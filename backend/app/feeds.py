from __future__ import annotations

import calendar
import hashlib
import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus

import feedparser
import httpx


@dataclass(frozen=True)
class FeedSource:
    id: str
    name: str
    url: str
    category: str
    provider: str = "publisher_rss"
    note: str | None = None


GOOGLE_BASE = "https://news.google.com/rss"
LOCALE = "hl=en-IN&gl=IN&ceid=IN:en"

def google_publisher_url(domain: str) -> str:
    query = quote_plus(f"site:{domain} when:2d")
    return f"{GOOGLE_BASE}/search?q={query}&{LOCALE}"


# Google News RSS is useful for discovery but is not an officially documented
# public API. Direct publisher feeds are preferred. Publisher-specific Google
# discovery is used only where an outlet blocks or does not expose direct RSS.
RSS_SOURCES: tuple[FeedSource, ...] = (
    FeedSource("google-top-in", "Google News India", f"{GOOGLE_BASE}?{LOCALE}", "India", "google_news_rss", "Undocumented RSS discovery feed"),
    FeedSource("google-world-in", "Google News · World", f"{GOOGLE_BASE}/headlines/section/topic/WORLD?{LOCALE}", "World", "google_news_rss"),
    FeedSource("google-business-in", "Google News · Business", f"{GOOGLE_BASE}/headlines/section/topic/BUSINESS?{LOCALE}", "Business", "google_news_rss"),
    FeedSource("google-technology-in", "Google News · Technology", f"{GOOGLE_BASE}/headlines/section/topic/TECHNOLOGY?{LOCALE}", "Technology", "google_news_rss"),
    FeedSource("google-science-in", "Google News · Science", f"{GOOGLE_BASE}/headlines/section/topic/SCIENCE?{LOCALE}", "Science", "google_news_rss"),
    FeedSource("google-sports-in", "Google News · Sports", f"{GOOGLE_BASE}/headlines/section/topic/SPORTS?{LOCALE}", "Sports", "google_news_rss"),
    FeedSource("google-entertainment-in", "Google News · Entertainment", f"{GOOGLE_BASE}/headlines/section/topic/ENTERTAINMENT?{LOCALE}", "Entertainment", "google_news_rss"),

    # India-first direct publisher feeds (English and Hindi)
    FeedSource("aajtak-home", "Aaj Tak", "https://www.aajtak.in/rssfeeds/?id=home", "India", note="Direct Hindi RSS"),
    FeedSource("ndtv-latest", "NDTV", "https://feeds.feedburner.com/NDTV-LatestNews", "India", note="Direct latest-news RSS"),
    FeedSource("india-today", "India Today", "https://www.indiatoday.in/rss/1206578", "India", note="Direct India RSS"),
    FeedSource("abp-india-en", "ABP Live", "https://news.abplive.com/news/india/feed", "India", note="Direct English RSS"),
    FeedSource("abp-india-hi", "ABP News Hindi", "https://www.abplive.com/news/india/feed", "India", note="Direct Hindi RSS"),
    FeedSource("toi-india", "The Times of India", "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms", "India", note="Direct India RSS"),
    FeedSource("hindu-national", "The Hindu", "https://www.thehindu.com/news/national/feeder/default.rss", "India", note="Direct national RSS"),
    FeedSource("hindustan-times-india", "Hindustan Times", "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml", "India", note="Direct India RSS"),
    FeedSource("india-tv-top", "India TV", "https://www.indiatvnews.com/rssnews/topstory.xml", "India", note="Direct top-stories RSS"),
    FeedSource("tv9-hindi", "TV9 Bharatvarsh", "https://www.tv9hindi.com/rss", "India", note="Direct Hindi RSS"),
    FeedSource("greater-kashmir", "Greater Kashmir", "https://www.greaterkashmir.com/feed/", "India", note="Direct Jammu and Kashmir RSS"),
    FeedSource("the-wire", "The Wire", "https://thewire.in/feed", "India", note="Direct feed"),
    FeedSource("scroll-india", "Scroll.in", "https://scroll.in/feed", "India", note="Direct feed"),

    # India-first fact-check feeds. These surface recently reviewed viral
    # social-media claims without scraping or monitoring individual profiles.
    FeedSource(
        "google-factchecks-en", "Google News · Viral Fact Checks",
        f"{GOOGLE_BASE}/search?q={quote_plus('fact check viral fake false misleading India when:2d')}&{LOCALE}",
        "Fact Check", "google_news_rss", "Broad recent fact-check discovery",
    ),
    FeedSource(
        "google-factchecks-hi", "Google News · Hindi Fact Checks",
        f"{GOOGLE_BASE}/search?q={quote_plus('फैक्ट चेक वायरल दावा फर्जी when:2d')}&hl=hi&gl=IN&ceid=IN:hi",
        "Fact Check", "google_news_rss", "Recent Hindi fact-check discovery",
    ),
    FeedSource("altnews-factchecks", "Alt News", "https://www.altnews.in/feed/", "Fact Check", note="Recent misinformation and viral-claim reviews"),
    FeedSource("boomlive-factchecks", "BOOM", "https://www.boomlive.in/feed", "Fact Check", note="Recent India-focused fact checks"),
    FeedSource("factly-factchecks", "FACTLY", "https://factly.in/feed/", "Fact Check", note="Recent public-claim and social-media fact checks"),
    FeedSource("newschecker-factchecks", "Newschecker", "https://newschecker.in/feed/", "Fact Check", note="Recent viral-claim reviews"),
    FeedSource("vishvasnews-factchecks", "Vishvas News", "https://www.vishvasnews.com/feed/", "Fact Check", note="Recent Hindi and India-focused fact checks"),
    FeedSource("factcrescendo-factchecks", "Fact Crescendo", "https://www.factcrescendo.com/feed/", "Fact Check", note="Recent misinformation reviews"),

    # Indian outlets whose direct feeds are blocked/unavailable to this server.
    # Google publisher discovery retains attribution and links to each outlet.
    FeedSource("zee-via-google", "Zee News · discovery", google_publisher_url("zeenews.india.com"), "India", "google_news_rss", "Publisher-specific Google discovery; direct RSS blocks server access"),
    FeedSource("news18-via-google", "News18 · discovery", google_publisher_url("news18.com"), "India", "google_news_rss", "Publisher-specific Google discovery"),
    FeedSource("indian-express-via-google", "Indian Express · discovery", google_publisher_url("indianexpress.com"), "India", "google_news_rss", "Publisher-specific Google discovery"),
    FeedSource("times-now-via-google", "Times Now · discovery", google_publisher_url("timesnownews.com"), "India", "google_news_rss", "Publisher-specific Google discovery"),
    FeedSource("theprint-via-google", "ThePrint · discovery", google_publisher_url("theprint.in"), "India", "google_news_rss", "Publisher-specific Google discovery"),
    FeedSource("republic-via-google", "Republic World · discovery", google_publisher_url("republicworld.com"), "India", "google_news_rss", "Publisher-specific Google discovery"),
    FeedSource("ddnews-via-google", "DD News · discovery", google_publisher_url("ddnews.gov.in"), "India", "google_news_rss", "Publisher-specific Google discovery"),
    FeedSource("wion-via-google", "WION · discovery", google_publisher_url("wionews.com"), "India", "google_news_rss", "Publisher-specific Google discovery"),
    FeedSource("daily-excelsior-via-google", "Daily Excelsior · discovery", google_publisher_url("dailyexcelsior.com"), "India", "google_news_rss", "Jammu and Kashmir publisher discovery"),

    FeedSource("bbc-world", "BBC News · World", "https://feeds.bbci.co.uk/news/world/rss.xml", "World"),
    FeedSource("bbc-business", "BBC News · Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "Business"),
    FeedSource("bbc-technology", "BBC News · Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml", "Technology"),
    FeedSource("bbc-science", "BBC News · Science", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "Science"),
    FeedSource("bbc-sport", "BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml", "Sports"),
    FeedSource("bbc-entertainment", "BBC News · Entertainment", "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", "Entertainment"),
    FeedSource("aljazeera", "Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "World"),
    FeedSource("nasa", "NASA", "https://www.nasa.gov/news-release/feed/", "Science"),
    FeedSource("techcrunch", "TechCrunch", "https://techcrunch.com/feed/", "Technology"),
)


def google_search_source(query: str, category: str | None = None) -> FeedSource:
    url = f"{GOOGLE_BASE}/search?q={quote_plus(query)}&{LOCALE}"
    return FeedSource(
        "google-search", "Google News search", url,
        category if category and category.lower() != "all" else "World",
        "google_news_rss", "Dynamic keyword discovery feed",
    )


def sources_for(category: str | None = None, query: str | None = None) -> list[FeedSource]:
    if query:
        # Dynamic Google discovery plus relevant direct publisher feeds to improve diversity.
        directs = [
            s for s in RSS_SOURCES
            if s.provider == "publisher_rss"
            and (not category or category.lower() == "all" or s.category.lower() == category.lower())
        ]
        return [google_search_source(query, category), *directs]
    if category and category.lower() != "all":
        return [s for s in RSS_SOURCES if s.category.lower() == category.lower()]
    return list(RSS_SOURCES)


def _text(value: str | None, max_length: int = 1200) -> str:
    if not value:
        return ""
    clean = re.sub(r"<[^>]+>", " ", value)
    clean = html.unescape(clean)
    return re.sub(r"\s+", " ", clean).strip()[:max_length]


def _published(entry: Any) -> str | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), UTC).isoformat()
    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return None
    return None


def _image(entry: Any) -> str | None:
    for key in ("media_content", "media_thumbnail"):
        media = entry.get(key) or []
        if media and isinstance(media, list):
            url = media[0].get("url")
            if url and str(url).startswith("http"):
                return str(url)
    for enclosure in entry.get("enclosures", []) or []:
        href = enclosure.get("href") or enclosure.get("url")
        kind = enclosure.get("type", "")
        if href and (kind.startswith("image/") or re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", href, re.I)):
            return str(href)
    return None


def _identity(headline: str) -> str:
    # Preserve Devanagari and other regional scripts; ASCII-only normalization
    # would collapse every Hindi headline to the same empty identifier.
    normalized = re.sub(r"[^\w]+", " ", headline.casefold(), flags=re.UNICODE)
    normalized = normalized.replace("_", " ").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def _source_and_title(entry: Any, feed: FeedSource) -> tuple[str, str]:
    title = _text(entry.get("title"), 400) or "Untitled article"
    source_obj = entry.get("source") or {}
    # Direct publisher feeds are already bound to a named registry source;
    # some misuse the RSS <source> field for an author name. Only discovery
    # feeds need to derive the publisher from each entry.
    source = ""
    if feed.provider == "google_news_rss":
        source = _text(source_obj.get("title") if hasattr(source_obj, "get") else "", 120)
        if " - " in title:
            possible_title, possible_source = title.rsplit(" - ", 1)
            source = source or possible_source.strip()
            title = possible_title.strip()
    return source or feed.name.split(" · ")[0], title


async def fetch_feed(
    client: httpx.AsyncClient,
    feed: FeedSource,
    max_items: int,
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        response = await client.get(feed.url)
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        if parsed.bozo and not parsed.entries:
            raise ValueError(str(parsed.bozo_exception))
        now = datetime.now(UTC).isoformat()
        articles: list[dict[str, Any]] = []
        for index, entry in enumerate(parsed.entries[:max_items]):
            source, headline = _source_and_title(entry, feed)
            link = str(entry.get("link") or "").strip()
            if not link or not headline:
                continue
            articles.append(
                {
                    "id": _identity(headline),
                    "headline": headline,
                    "description": _text(entry.get("summary") or entry.get("description")),
                    "source": source,
                    "provider": feed.provider,
                    "author": _text(entry.get("author"), 120) or None,
                    "url": link,
                    "image_url": _image(entry),
                    "category": feed.category,
                    "published_at": _published(entry),
                    "fetched_at": now,
                    "is_trending": index < 5,
                    "raw": {"feed_id": feed.id},
                }
            )
        return articles, None
    except Exception as exc:  # One broken feed must not take down the aggregator.
        return [], f"{feed.name}: {type(exc).__name__}"


async def fetch_rss_sources(
    feeds: list[FeedSource], timeout_seconds: int, max_items: int
) -> tuple[list[dict[str, Any]], list[str]]:
    headers = {
        "User-Agent": "TruthScanAI/1.0 (+news aggregation prototype; contact: local-demo)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    }
    timeout = httpx.Timeout(timeout_seconds)
    async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
        results = await __import__("asyncio").gather(
            *(fetch_feed(client, feed, max_items) for feed in feeds)
        )
    articles: list[dict[str, Any]] = []
    warnings: list[str] = []
    for batch, warning in results:
        articles.extend(batch)
        if warning:
            warnings.append(warning)
    # Keep the first appearance from this refresh. Repository IDs also deduplicate over time.
    unique = {article["id"]: article for article in reversed(articles)}
    return list(reversed(unique.values())), warnings
