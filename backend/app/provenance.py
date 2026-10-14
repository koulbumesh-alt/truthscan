from __future__ import annotations

import re
from typing import Any

from .factchecks import NEGATIVE_RATING_WORDS, POSITIVE_RATING_WORDS

# “Verified” means deliberately included in TRUTHSCAN's reviewed publisher
# registry. It does not mean that every statement is infallible; an attributed
# correction or debunk always takes precedence.
RECOGNIZED_PUBLISHERS = {
    "aaj tak", "ndtv", "india today", "abp live", "abp news hindi",
    "the times of india", "times of india", "the hindu", "hindustan times",
    "india tv", "tv9 bharatvarsh", "greater kashmir", "the wire", "scroll in",
    "zee news", "news18", "indian express", "the indian express", "times now",
    "theprint", "republic world", "dd news", "wion", "daily excelsior",
    "bbc news", "bbc sport", "al jazeera", "nasa", "techcrunch",
}

FEED_DEBUNKED = "DEBUNKED BY FACT-CHECKERS"
FEED_SUPPORTED = "SUPPORTED BY VERIFIED NEWS SOURCE"
FEED_MORE = "MORE VERIFICATION NEEDED"


def publisher_key(value: str | None) -> str:
    text = (value or "").casefold().replace("&", " and ")
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def recognized_publisher(value: str | None) -> bool:
    return publisher_key(value) in RECOGNIZED_PUBLISHERS


def feed_verdict(article: dict[str, Any]) -> tuple[str, str]:
    """Return a transparent feed-level status without inventing a truth score.

    A full verification can supersede this lightweight source/wording status.
    """
    source = str(article.get("source") or "the named publisher").strip()
    category = str(article.get("category") or "").casefold()
    text = f"{article.get('headline') or ''} {article.get('description') or ''}".casefold()

    if category == "fact check":
        if any(word in text for word in NEGATIVE_RATING_WORDS):
            return (
                FEED_DEBUNKED,
                f"The attributed fact-check review from {source} explicitly describes the matching claim as false, manipulated, misleading, or out of context.",
            )
        if any(word in text for word in POSITIVE_RATING_WORDS):
            return (
                FEED_SUPPORTED,
                f"The attributed fact-check review from {source} explicitly supports the matching claim. Open the in-app evidence report to inspect the reviewed wording.",
            )
        return (
            FEED_MORE,
            f"{source} published a fact-check review, but its feed headline does not expose a clear positive or negative conclusion. TRUTHSCAN will inspect the complete evidence in-app.",
        )

    if recognized_publisher(source) or bool(article.get("recognized_publisher")):
        return (
            FEED_SUPPORTED,
            f"This report was published by {source}, a publisher in TRUTHSCAN's reviewed source registry. Support is provisional and can be superseded by a correction or attributed debunk.",
        )

    return (
        FEED_MORE,
        "The feed item alone does not establish a close attributed debunk or a strongly matching report from TRUTHSCAN's reviewed source registry. Run the in-app evidence check.",
    )
