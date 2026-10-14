from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any

from .config import Settings
from .database import NewsRepository
from .feeds import RSS_SOURCES, fetch_rss_sources, sources_for
from .providers import fetch_gnews, fetch_newsapi
from .recency import is_recent_rumour


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "have", "in", "is", "it", "its", "new", "news", "of", "on",
    "or", "that", "the", "their", "this", "to", "was", "were", "will",
    "with", "after", "about", "over", "says", "said", "latest", "live",
}


def _normalized(value: str) -> str:
    # Unicode-aware so searches can retain Hindi and other regional scripts.
    return " ".join(re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE))


def _tokens(value: str) -> set[str]:
    words = re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE)
    useful = {word for word in words if word not in STOP_WORDS and len(word) > 1}
    return useful or set(words)


def _published_timestamp(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp()
    except (TypeError, ValueError):
        return 0.0


class NewsService:
    def __init__(self, repository: NewsRepository, settings: Settings):
        self.repository = repository
        self.settings = settings
        self._refresh_lock = asyncio.Lock()
        self.last_warnings: list[str] = []

    @staticmethod
    def _cache_key(query: str | None, category: str | None) -> str:
        q = (query or "").strip().lower()
        cat = (category or "all").strip().lower()
        # Versioned so source-registry changes invalidate earlier feed snapshots.
        return f"news:v4:{cat}:{q}"

    async def refresh(
        self,
        query: str | None = None,
        category: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        cache_key = self._cache_key(query, category)
        if not force and self.repository.cache_is_fresh(
            cache_key, self.settings.cache_ttl_seconds
        ):
            row = self.repository.cache_info(cache_key)
            return {
                "fetched": 0,
                "stored": 0,
                "new_items": 0,
                "updated_items": 0,
                "cached": True,
                "refreshed_at": row["refreshed_at"] if row else None,
                "warnings": [],
            }

        async with self._refresh_lock:
            # Another request may have refreshed while this one waited.
            if not force and self.repository.cache_is_fresh(
                cache_key, self.settings.cache_ttl_seconds
            ):
                row = self.repository.cache_info(cache_key)
                return {
                    "fetched": 0,
                    "stored": 0,
                    "new_items": 0,
                    "updated_items": 0,
                    "cached": True,
                    "refreshed_at": row["refreshed_at"] if row else None,
                    "warnings": [],
                }

            feeds = sources_for(category=category, query=query)
            rss_task = fetch_rss_sources(
                feeds,
                self.settings.request_timeout_seconds,
                self.settings.max_articles_per_feed,
            )
            gnews_task = fetch_gnews(
                self.settings.gnews_api_key,
                query,
                category,
                self.settings.request_timeout_seconds,
            )
            newsapi_task = fetch_newsapi(
                self.settings.newsapi_key,
                query,
                category,
                self.settings.request_timeout_seconds,
            )
            (rss_articles, rss_warnings), (gnews_articles, gnews_warning), (
                newsapi_articles,
                newsapi_warning,
            ) = await asyncio.gather(rss_task, gnews_task, newsapi_task)

            all_articles = [*rss_articles, *gnews_articles, *newsapi_articles]
            # Last write wins for same normalized headline; favor key-based APIs,
            # then publisher feeds, over the Google redirect record.
            rank = {"google_news_rss": 0, "publisher_rss": 1, "newsapi": 2, "gnews_api": 3}
            unique: dict[str, dict[str, Any]] = {}
            for article in sorted(all_articles, key=lambda a: rank.get(a["provider"], 0)):
                unique[article["id"]] = article
            existing = self.repository.existing_ids(list(unique))
            new_items = len(set(unique) - existing)
            updated_items = len(set(unique) & existing)
            stored = self.repository.upsert_many(list(unique.values()))
            warnings = [*rss_warnings]
            if gnews_warning:
                warnings.append(gnews_warning)
            if newsapi_warning:
                warnings.append(newsapi_warning)
            refreshed_at = self.repository.mark_refresh(cache_key, len(all_articles))
            self.repository.prune(days=30)
            self.last_warnings = warnings[-20:]
            return {
                "fetched": len(all_articles),
                "stored": stored,
                "new_items": new_items,
                "updated_items": updated_items,
                "cached": False,
                "refreshed_at": refreshed_at,
                "warnings": warnings,
            }

    @staticmethod
    def _score_article(query: str, article: dict[str, Any]) -> float:
        """Transparent lexical relevance score.

        Google News performs broad discovery; this local score then puts close
        headline matches first and keeps looser contextual matches below them.
        It is deliberately deterministic rather than an opaque AI ranking.
        """
        query_norm = _normalized(query)
        title_norm = _normalized(article.get("headline", ""))
        description = article.get("description", "") or ""
        source = article.get("source", "") or ""
        query_terms = _tokens(query)
        title_terms = _tokens(title_norm)
        description_terms = _tokens(description)
        source_terms = _tokens(source)
        if not query_terms:
            return 0.0

        title_overlap = len(query_terms & title_terms) / len(query_terms)
        description_overlap = len(query_terms & description_terms) / len(query_terms)
        title_precision = len(query_terms & title_terms) / max(1, len(title_terms))
        source_overlap = len(query_terms & source_terms) / len(query_terms)
        exact_phrase = bool(
            query_norm
            and len(query_norm) > 2
            and (query_norm in title_norm or title_norm in query_norm)
        )

        score = (
            title_overlap * 58
            + description_overlap * 17
            + min(title_precision, 1.0) * 10
            + source_overlap * 5
            + (22 if exact_phrase else 0)
            + (3 if article.get("is_trending") else 0)
        )
        published = _published_timestamp(article.get("published_at"))
        if published:
            age_days = max(0.0, (datetime.now(UTC).timestamp() - published) / 86_400)
            score += max(0.0, 5.0 - min(age_days, 10.0) * 0.5)
        return round(min(100.0, score), 1)

    def _rank_search(
        self, query: str, articles: list[dict[str, Any]], sort: str
    ) -> list[dict[str, Any]]:
        scored: list[dict[str, Any]] = []
        for article in articles:
            item = dict(article)
            item["relevance_score"] = self._score_article(query, item)
            # SQL already ensures a textual overlap. This threshold removes
            # accidental matches caused only by generic description words.
            if item["relevance_score"] >= 8:
                scored.append(item)

        scored.sort(
            key=lambda item: (
                item["relevance_score"],
                bool(item.get("is_trending")),
                _published_timestamp(item.get("published_at")),
            ),
            reverse=True,
        )
        # Keep a concise "best" group; the remainder is useful related coverage.
        for index, item in enumerate(scored):
            item["match_type"] = "best" if index < 6 else "related"

        if sort == "newest":
            scored.sort(
                key=lambda item: (
                    item["match_type"] == "best",
                    _published_timestamp(item.get("published_at")),
                ),
                reverse=True,
            )
        elif sort == "trending":
            scored.sort(
                key=lambda item: (
                    item["match_type"] == "best",
                    bool(item.get("is_trending")),
                    item["relevance_score"],
                ),
                reverse=True,
            )
        return scored

    async def list_articles(
        self,
        query: str | None,
        category: str | None,
        sort: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        refresh = await self.refresh(query=query, category=category)
        if query and query.strip():
            candidates = self.repository.search(
                query=query,
                category=category,
                sort="newest",
                limit=300,
                offset=0,
            )
            # Search may include fact-check feed entries, but the rumours desk
            # is intentionally current: never surface an old review as though
            # it describes a newly circulating claim.
            candidates = [
                row for row in candidates
                if row.get("category") != "Fact Check"
                or is_recent_rumour(row.get("published_at"))
            ]
            ranked = self._rank_search(query, candidates, sort)
            articles = ranked[offset : offset + limit]
        else:
            articles = self.repository.search(
                query=None,
                category=category,
                sort=sort,
                limit=limit,
                offset=offset,
            )
        return articles, refresh

    def source_status(self) -> list[dict[str, Any]]:
        result = [
            {
                "id": feed.id,
                "name": feed.name,
                "kind": "rss",
                "category": feed.category,
                "enabled": True,
                "requires_key": False,
                "note": feed.note,
            }
            for feed in RSS_SOURCES
        ]
        result.extend(
            [
                {
                    "id": "gnews-api",
                    "name": "GNews API",
                    "kind": "api",
                    "category": "All",
                    "enabled": bool(self.settings.gnews_api_key),
                    "requires_key": True,
                    "note": "Optional adapter; set GNEWS_API_KEY.",
                },
                {
                    "id": "newsapi",
                    "name": "NewsAPI",
                    "kind": "api",
                    "category": "All",
                    "enabled": bool(self.settings.newsapi_key),
                    "requires_key": True,
                    "note": "Optional adapter; set NEWSAPI_KEY.",
                },
                {
                    "id": "google-fact-check-tools",
                    "name": "Google Fact Check Tools API",
                    "kind": "api",
                    "category": "Fact Check",
                    "enabled": bool(self.settings.google_fact_check_api_key),
                    "requires_key": True,
                    "note": "Recommended for structured publisher ratings; fallback fact-check discovery works without it.",
                },
            ]
        )
        return result

    def enabled_providers(self) -> list[str]:
        providers = ["Google News RSS", "Publisher RSS", "Fact-check publisher RSS", "Fact-check article discovery"]
        if self.settings.google_fact_check_api_key:
            providers.append("Google Fact Check Tools API")
        if self.settings.youtube_api_key:
            providers.append("YouTube Data API")
        if self.settings.gemini_api_key:
            providers.append("Gemini video understanding")
        if self.settings.x_bearer_token:
            providers.append("X API v2")
        if self.settings.meta_access_token:
            providers.append(f"Meta Graph API {self.settings.meta_graph_version}")
        if self.settings.gnews_api_key:
            providers.append("GNews API")
        if self.settings.newsapi_key:
            providers.append("NewsAPI")
        return providers
