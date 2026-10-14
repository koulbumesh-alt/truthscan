from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import httpx


def _id(title: str) -> str:
    return hashlib.sha256(title.lower().strip().encode()).hexdigest()[:24]


def _iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


async def fetch_gnews(
    api_key: str, query: str | None, category: str | None, timeout: int
) -> tuple[list[dict[str, Any]], str | None]:
    if not api_key:
        return [], None
    endpoint = "search" if query else "top-headlines"
    params: dict[str, Any] = {"apikey": api_key, "lang": "en", "country": "in", "max": 25}
    if query:
        params["q"] = query
    elif category and category.lower() != "all":
        params["category"] = category.lower()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"https://gnews.io/api/v4/{endpoint}", params=params)
            response.raise_for_status()
            payload = response.json()
        now = datetime.now(UTC).isoformat()
        result = []
        for index, item in enumerate(payload.get("articles", [])):
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if not title or not url:
                continue
            source = item.get("source") or {}
            result.append({
                "id": _id(title), "headline": title,
                "description": str(item.get("description") or "")[:1200],
                "source": str(source.get("name") or "GNews source"),
                "provider": "gnews_api", "author": None, "url": url,
                "image_url": item.get("image"), "category": category or "World",
                "published_at": _iso(item.get("publishedAt")), "fetched_at": now,
                "is_trending": index < 5, "raw": {"provider": "gnews"},
            })
        return result, None
    except Exception as exc:
        return [], f"GNews API: {type(exc).__name__}"


async def fetch_newsapi(
    api_key: str, query: str | None, category: str | None, timeout: int
) -> tuple[list[dict[str, Any]], str | None]:
    if not api_key:
        return [], None
    endpoint = "everything" if query else "top-headlines"
    params: dict[str, Any] = {"pageSize": 25, "language": "en"}
    if query:
        params.update({"q": query, "sortBy": "publishedAt"})
    else:
        params["country"] = "in"
        if category and category.lower() not in ("all", "world", "science"):
            params["category"] = category.lower()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"https://newsapi.org/v2/{endpoint}",
                params=params,
                headers={"X-Api-Key": api_key},
            )
            response.raise_for_status()
            payload = response.json()
        now = datetime.now(UTC).isoformat()
        result = []
        for index, item in enumerate(payload.get("articles", [])):
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if not title or not url or title == "[Removed]":
                continue
            source = item.get("source") or {}
            result.append({
                "id": _id(title), "headline": title,
                "description": str(item.get("description") or "")[:1200],
                "source": str(source.get("name") or "NewsAPI source"),
                "provider": "newsapi", "author": item.get("author"), "url": url,
                "image_url": item.get("urlToImage"), "category": category or "World",
                "published_at": _iso(item.get("publishedAt")), "fetched_at": now,
                "is_trending": index < 5, "raw": {"provider": "newsapi"},
            })
        return result, None
    except Exception as exc:
        return [], f"NewsAPI: {type(exc).__name__}"
