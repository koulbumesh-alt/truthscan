from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from .feeds import fetch_rss_sources, google_search_source
from .recency import is_recent_rumour

FACT_CHECKER_NAMES = (
    "alt news",
    "boom",
    "factly",
    "newschecker",
    "vishvas news",
    "vishvasnews",
    "the quint",
    "webqoof",
    "india today fact check",
    "afp fact check",
    "fact crescendo",
    "factcrescendo",
    "pib fact check",
    "thip media",
    "dfrac",
    "logically facts",
    "newsmobile",
)

NEGATIVE_RATING_WORDS = (
    "false", "fake", "misleading", "incorrect", "not true", "fabricated",
    "altered", "morphed", "manipulated", "unrelated", "old video", "old image",
    "out of context", "not declared", "did not", "was not", "no evidence", "hoax",
    "ai-generated", "ai generated", "deepfake", "synthetic media",
    "फर्जी", "झूठ", "भ्रामक", "गलत", "फेक", "पुराना वीडियो",
)
POSITIVE_RATING_WORDS = (
    "true", "correct", "accurate", "supported", "सही", "सच", "सत्य",
)


def rating_kind(rating: str) -> str:
    value = rating.casefold()
    if any(word in value for word in NEGATIVE_RATING_WORDS):
        return "negative"
    if any(word in value for word in POSITIVE_RATING_WORDS):
        return "positive"
    return "unknown"


def _recognized_fact_checker(source: str, title: str) -> bool:
    value = f"{source} {title}".casefold()
    return any(name in value for name in FACT_CHECKER_NAMES)


def _rating_from_article(title: str, description: str) -> str:
    text = f"{title} {description}".casefold()
    if any(word in text for word in NEGATIVE_RATING_WORDS):
        return "False or misleading claim"
    if any(word in text for word in POSITIVE_RATING_WORDS):
        return "Supported by fact-check"
    return "Fact-check review available"


async def fetch_structured_fact_checks(
    api_key: str,
    query: str,
    timeout: int,
) -> tuple[list[dict[str, Any]], str | None]:
    if not api_key:
        return [], None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                "https://factchecktools.googleapis.com/v1alpha1/claims:search",
                params={"query": query, "pageSize": 20, "key": api_key},
            )
            response.raise_for_status()
            payload = response.json()
        reviews: list[dict[str, Any]] = []
        for claim in payload.get("claims", []):
            for review in claim.get("claimReview", []):
                publisher = review.get("publisher") or {}
                url = str(review.get("url") or "").strip()
                if not url:
                    continue
                reviews.append(
                    {
                        "publisher": str(publisher.get("name") or publisher.get("site") or "Fact checker"),
                        "site": publisher.get("site"),
                        "rating": str(review.get("textualRating") or "Reviewed"),
                        "title": str(review.get("title") or claim.get("text") or "Fact-check review"),
                        "url": url,
                        "review_date": review.get("reviewDate"),
                        "claim_text": claim.get("text"),
                        "claimant": claim.get("claimant"),
                        "language_code": review.get("languageCode"),
                        "structured": True,
                    }
                )
        return reviews, None
    except Exception as exc:
        return [], f"Google Fact Check API: {type(exc).__name__}"


async def fetch_fact_check_discovery(
    query: str,
    timeout: int,
) -> tuple[list[dict[str, Any]], str | None]:
    # This is a fallback when no structured API key is configured. It only
    # labels an item as a fact check when the publisher is in the explicit
    # allowlist above; ordinary opinion/news pages are not treated as debunks.
    # Do not quote the entire claim: headlines often paraphrase it, and an
    # exact-phrase query misses otherwise relevant debunks.
    source = google_search_source(f"{query} fact check when:14d")
    articles, warnings = await fetch_rss_sources([source], timeout, 50)
    reviews: list[dict[str, Any]] = []
    for article in articles:
        if not _recognized_fact_checker(article.get("source", ""), article.get("headline", "")):
            continue
        reviews.append(
            {
                "publisher": article.get("source") or "Fact checker",
                "site": None,
                "rating": _rating_from_article(
                    article.get("headline", ""), article.get("description", "")
                ),
                "title": article.get("headline") or "Fact-check review",
                "url": article.get("url") or "",
                "review_date": article.get("published_at"),
                "claim_text": None,
                "claimant": None,
                "language_code": None,
                "structured": False,
            }
        )
    return reviews, warnings[0] if warnings else None


async def search_fact_checks(
    query: str,
    api_key: str,
    timeout: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    structured, discovered = await asyncio.gather(
        fetch_structured_fact_checks(api_key, query, timeout),
        fetch_fact_check_discovery(query, timeout),
    )
    combined = [*structured[0], *discovered[0]]
    unique: dict[str, dict[str, Any]] = {}
    for review in combined:
        # A fresh search must not present an old debunk as a current rumour.
        # Unknown dates are excluded because retrieval time cannot establish
        # when the publisher actually reviewed the claim.
        if not is_recent_rumour(review.get("review_date")):
            continue
        key = re.sub(r"#.*$", "", review["url"]).rstrip("/")
        # Structured reviews supersede discovery-only records for the same URL.
        if key not in unique or review.get("structured"):
            unique[key] = review
    warnings = [warning for warning in (structured[1], discovered[1]) if warning]
    return list(unique.values())[:20], warnings
