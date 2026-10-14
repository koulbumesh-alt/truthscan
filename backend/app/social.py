from __future__ import annotations

import asyncio
import html
import json
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx


class SocialContentUnavailableError(RuntimeError):
    pass


class VideoAnalysisUnavailableError(RuntimeError):
    pass


def platform_for_url(url: str) -> str | None:
    host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
    if host in {"youtube.com", "m.youtube.com", "youtu.be"}:
        return "YouTube"
    if host in {"tiktok.com", "m.tiktok.com", "vm.tiktok.com"} or host.endswith(".tiktok.com"):
        return "TikTok"
    if host in {"x.com", "twitter.com", "mobile.twitter.com"}:
        return "X"
    if host in {"instagram.com", "m.instagram.com"}:
        return "Instagram"
    if host in {"facebook.com", "m.facebook.com", "fb.watch"}:
        return "Facebook"
    if host in {"reddit.com", "old.reddit.com", "redd.it"} or host.endswith(".reddit.com"):
        return "Reddit"
    return None


def _plain(value: str | None, limit: int = 5_000) -> str:
    if not value:
        return ""
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", value, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()[:limit]


def _youtube_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    if host == "youtu.be":
        return parsed.path.strip("/").split("/")[0] or None
    if host.endswith("youtube.com"):
        if parsed.path == "/watch":
            return (parse_qs(parsed.query).get("v") or [None])[0]
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
            return parts[1]
    return None


def _x_post_id(url: str) -> str | None:
    match = re.search(r"/(?:status|statuses)/(\d{1,19})(?:[/?#]|$)", url)
    return match.group(1) if match else None


def _facebook_object_id(url: str) -> str | None:
    parsed = urlparse(url)
    query_id = (parse_qs(parsed.query).get("v") or [None])[0]
    if query_id and str(query_id).isdigit():
        return str(query_id)
    patterns = (
        r"/(?:posts|reel|reels|videos)/(?:[^/?#]+/)?(\d+)(?:[/?#]|$)",
        r"/permalink\.php.*?[?&]story_fbid=(\d+)",
        r"/story\.php.*?[?&]story_fbid=(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, url, flags=re.I)
        if match:
            return match.group(1)
    return None


def _normalized_permalink(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    return f"{host}{path}".casefold()


def _result(
    platform: str,
    url: str,
    title: str,
    author: str | None,
    description: str | None,
    published_at: str | None,
    resolver: str,
    thumbnail_url: str | None = None,
) -> dict[str, Any]:
    return {
        "platform": platform,
        "source_url": url,
        "title": _plain(title, 500),
        "author": _plain(author, 200) or None,
        "description": _plain(description, 5_000) or None,
        "published_at": published_at,
        "resolver": resolver,
        "thumbnail_url": thumbnail_url,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "official_api_access_used": False,
        "official_api_provider": None,
        "official_api_note": None,
        "audiovisual_content_analyzed": False,
        "content_analysis_provider": None,
        "content_summary": None,
        "extracted_claims": [],
        "visible_text": [],
        "content_analysis_notes": None,
        "content_analysis_error": None,
    }


YOUTUBE_ANALYSIS_PROMPT = """Analyze the actual audio and visible frames of this news-related video.
Return JSON with exactly these fields:
- summary: a short factual summary of what the video says or shows
- claims: up to 5 specific, externally verifiable factual claims stated or visibly presented in the video, ordered with the video's main claim first
- visible_text: up to 8 important pieces of on-screen text relevant to those claims
- caveats: any language, audio, visibility, clipping, satire, or context limitation
Do not decide whether a claim is true or false. Do not treat the uploader or speaker as evidence. Exclude opinions, greetings, promotions, and vague rhetoric. Preserve names, places, dates, quantities, and the language of important claims where practical."""


def _parsed_video_analysis(raw: str, model: str, provider_suffix: str = "") -> dict[str, Any]:
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
    parsed = json.loads(raw)
    claims = [
        _plain(str(item), 600)
        for item in parsed.get("claims", [])
        if _plain(str(item), 600)
    ][:5]
    visible = [
        _plain(str(item), 300)
        for item in parsed.get("visible_text", [])
        if _plain(str(item), 300)
    ][:8]
    summary = _plain(str(parsed.get("summary") or ""), 2_000)
    caveats = _plain(str(parsed.get("caveats") or ""), 1_000)
    if not summary and not claims:
        raise VideoAnalysisUnavailableError(
            "Gemini processed the video but did not return a usable spoken or visible factual claim."
        )
    suffix = f" · {provider_suffix}" if provider_suffix else ""
    return {
        "audiovisual_content_analyzed": True,
        "content_analysis_provider": f"Google Gemini video understanding ({model}){suffix}",
        "content_summary": summary or None,
        "extracted_claims": claims,
        "visible_text": visible,
        "content_analysis_notes": caveats or None,
        "content_analysis_error": None,
    }


def _interaction_output_text(payload: dict[str, Any]) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    texts: list[str] = []
    for step in payload.get("steps") or []:
        if step.get("type") not in {"model_output", "output", "message"}:
            continue
        content = step.get("content") or []
        if isinstance(content, dict):
            content = [content]
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                texts.append(str(item["text"]))
    return "\n".join(texts)


async def _youtube_video_analysis_background(
    url: str,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    """Run long video work as a Gemini background interaction and poll it."""
    endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
        "Api-Revision": "2026-05-20",
    }
    payload = {
        "model": model,
        "input": [
            {"type": "video", "uri": url, "mime_type": "video/mp4"},
            {"type": "text", "text": YOUTUBE_ANALYSIS_PROMPT},
        ],
        "background": True,
        "generation_config": {"thinking_level": "low"},
    }
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30, connect=15), follow_redirects=True
    ) as client:
        response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        interaction = response.json()
        interaction_id = interaction.get("id")
        if not interaction_id:
            raise VideoAnalysisUnavailableError(
                "Gemini did not return a background-analysis job ID."
            )
        deadline = time.monotonic() + 600
        while interaction.get("status") in {None, "queued", "in_progress"}:
            if time.monotonic() >= deadline:
                raise VideoAnalysisUnavailableError(
                    "Gemini background video analysis did not finish within 10 minutes. Try a shorter public clip or paste the transcript."
                )
            await asyncio.sleep(5)
            response = await client.get(
                f"{endpoint}/{interaction_id}", headers=headers
            )
            response.raise_for_status()
            interaction = response.json()
    if interaction.get("status") != "completed":
        raise VideoAnalysisUnavailableError(
            "Gemini background video analysis ended without completing. The video may be restricted or unsupported."
        )
    raw = _interaction_output_text(interaction)
    if not raw:
        raise VideoAnalysisUnavailableError(
            "Gemini completed background processing but returned no readable analysis."
        )
    return _parsed_video_analysis(raw, model, "background processing")


async def _youtube_video_analysis(
    url: str,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    """Extract claims from actual audio/frames, escalating long work safely."""
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"file_data": {"file_uri": url, "mime_type": "video/*"}},
                {"text": YOUTUBE_ANALYSIS_PROMPT},
            ],
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1,
            "thinkingConfig": {"thinkingLevel": "low"},
        },
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(45, connect=15), follow_redirects=True
        ) as client:
            response = await client.post(
                endpoint,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
    except httpx.TimeoutException:
        # Google's guidance recommends background execution for long videos.
        return await _youtube_video_analysis_background(url, api_key, model)
    candidates = response.json().get("candidates") or []
    parts = (candidates[0].get("content") or {}).get("parts") or [] if candidates else []
    raw = next((str(part.get("text")) for part in parts if part.get("text")), "")
    if not raw:
        raise VideoAnalysisUnavailableError(
            "Gemini returned no readable audio/frame analysis for this video."
        )
    return _parsed_video_analysis(raw, model, "direct processing")


async def _youtube(client: httpx.AsyncClient, url: str, api_key: str) -> dict[str, Any]:
    video_id = _youtube_id(url)
    if not video_id:
        raise SocialContentUnavailableError("The YouTube video ID could not be read from this link.")
    if api_key:
        response = await client.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet,contentDetails", "id": video_id, "key": api_key},
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        if items:
            snippet = items[0].get("snippet", {})
            thumbs = snippet.get("thumbnails") or {}
            thumb = (thumbs.get("high") or thumbs.get("medium") or {}).get("url")
            return _result(
                "YouTube", url, snippet.get("title", ""), snippet.get("channelTitle"),
                snippet.get("description"), snippet.get("publishedAt"),
                "YouTube Data API (live metadata)", thumb,
            )
    response = await client.get(
        "https://www.youtube.com/oembed", params={"url": url, "format": "json"}
    )
    response.raise_for_status()
    data = response.json()
    return _result(
        "YouTube", url, data.get("title", ""), data.get("author_name"), None, None,
        "YouTube oEmbed (live public metadata)", data.get("thumbnail_url"),
    )


async def _tiktok(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get("https://www.tiktok.com/oembed", params={"url": url})
    response.raise_for_status()
    data = response.json()
    return _result(
        "TikTok", url, data.get("title", ""), data.get("author_name"),
        None, None, "TikTok oEmbed (live public metadata)", data.get("thumbnail_url"),
    )


async def _x_oembed(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get(
        "https://publish.twitter.com/oembed",
        params={"url": url, "omit_script": "true", "dnt": "true"},
    )
    response.raise_for_status()
    data = response.json()
    post_text = _plain(data.get("html"), 1_000)
    # Embedded HTML may end with the author and date; it is still preferable
    # to a generic login-page title and is shown to the user for review.
    return _result(
        "X", url, post_text, data.get("author_name"), None, None,
        "X oEmbed (live public post)", None,
    )


async def _x_api(
    client: httpx.AsyncClient,
    url: str,
    bearer_token: str,
) -> dict[str, Any]:
    post_id = _x_post_id(url)
    if not post_id:
        raise SocialContentUnavailableError("The X post ID could not be read from this link.")
    response = await client.get(
        f"https://api.x.com/2/tweets/{post_id}",
        headers={"Authorization": f"Bearer {bearer_token}"},
        params={
            "post.fields": "attachments,author_id,created_at,entities,lang,article,article_title,media_metadata",
            "expansions": "author_id,attachments.media_keys",
            "user.fields": "name,username",
            "media.fields": "type,url,preview_image_url,alt_text,variants",
        },
    )
    response.raise_for_status()
    payload = response.json()
    post = payload.get("data") or {}
    text = _plain(post.get("text"), 2_000)
    if not text:
        raise ValueError("X API returned no readable post text.")
    users = (payload.get("includes") or {}).get("users") or []
    author_data = next(
        (item for item in users if str(item.get("id")) == str(post.get("author_id"))),
        users[0] if users else {},
    )
    username = _plain(author_data.get("username"), 100)
    author_name = _plain(author_data.get("name"), 150)
    author = author_name + (f" (@{username})" if username else "")
    media = (payload.get("includes") or {}).get("media") or []
    thumbnail = next(
        (
            item.get("preview_image_url") or item.get("url")
            for item in media
            if item.get("preview_image_url") or item.get("url")
        ),
        None,
    )
    description_parts = [
        _plain(post.get("article_title"), 500),
        *[_plain(item.get("alt_text"), 500) for item in media if item.get("alt_text")],
    ]
    result = _result(
        "X", url, text, author or None,
        " · ".join(item for item in description_parts if item) or None,
        post.get("created_at"), "X API v2 Post lookup (live public post)", thumbnail,
    )
    result.update({
        "official_api_access_used": True,
        "official_api_provider": "X API v2",
        "official_api_note": "Post text and available author/media metadata were retrieved through the configured X developer access.",
    })
    return result


async def _x(
    client: httpx.AsyncClient,
    url: str,
    bearer_token: str,
) -> dict[str, Any]:
    if bearer_token:
        try:
            return await _x_api(client, url, bearer_token)
        except (httpx.HTTPError, ValueError, KeyError):
            result = await _x_oembed(client, url)
            result["official_api_note"] = (
                "Configured X API access did not return this post; the official public oEmbed response was used instead."
            )
            return result
    result = await _x_oembed(client, url)
    result["official_api_note"] = (
        "X_BEARER_TOKEN is not configured; the official public oEmbed response was used."
    )
    return result


async def _facebook_graph(
    client: httpx.AsyncClient,
    url: str,
    access_token: str,
    graph_version: str,
) -> dict[str, Any]:
    object_id = _facebook_object_id(url)
    if not object_id:
        raise SocialContentUnavailableError(
            "The Facebook post or video ID could not be read from this URL. Use the full post, video, or Reel URL instead of a short share link."
        )
    endpoint = f"https://graph.facebook.com/{graph_version}/{object_id}"
    field_sets = (
        "message,created_time,permalink_url,full_picture,from",
        "description,title,created_time,permalink_url,picture,from",
    )
    last_error: Exception | None = None
    data: dict[str, Any] | None = None
    for fields in field_sets:
        try:
            response = await client.get(
                endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
                params={"fields": fields},
            )
            response.raise_for_status()
            data = response.json()
            break
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
    if not data:
        raise SocialContentUnavailableError(
            "Meta Graph API could not read this Facebook item with the configured token. Confirm live-mode App Review, business verification, and Page Public Content Access or Page permissions."
        ) from last_error
    title = _plain(
        data.get("message") or data.get("description") or data.get("title"),
        2_000,
    )
    if not title:
        raise SocialContentUnavailableError(
            "Meta Graph API returned the Facebook item but did not expose analyzable post text."
        )
    author_data = data.get("from") or {}
    result = _result(
        "Facebook", url, title, author_data.get("name"),
        data.get("description") if data.get("message") else None,
        data.get("created_time"),
        f"Meta Graph API {graph_version} (approved Page access)",
        data.get("full_picture") or data.get("picture"),
    )
    result.update({
        "official_api_access_used": True,
        "official_api_provider": f"Meta Graph API {graph_version}",
        "official_api_note": "Facebook content was retrieved through the configured Meta token and its approved Page permissions.",
    })
    return result


async def _instagram_graph(
    client: httpx.AsyncClient,
    url: str,
    access_token: str,
    graph_version: str,
    instagram_account_id: str,
) -> dict[str, Any]:
    if not instagram_account_id:
        raise SocialContentUnavailableError(
            "META_INSTAGRAM_ACCOUNT_ID is not configured. Official Instagram media lookup requires an authorized professional-account ID and an approved Meta token."
        )
    endpoint = f"https://graph.facebook.com/{graph_version}/{instagram_account_id}/media"
    target = _normalized_permalink(url)
    after: str | None = None
    for _page in range(5):
        params = {
            "fields": "id,caption,media_type,media_product_type,permalink,thumbnail_url,timestamp,username",
            "limit": "100",
        }
        if after:
            params["after"] = after
        try:
            response = await client.get(
                endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SocialContentUnavailableError(
                "Meta Graph API could not list Instagram media with the configured account and token. Confirm Instagram permissions, App Review, and token validity."
            ) from exc
        for item in payload.get("data") or []:
            if _normalized_permalink(str(item.get("permalink") or "")) != target:
                continue
            caption = _plain(item.get("caption"), 5_000)
            if not caption:
                raise SocialContentUnavailableError(
                    "The Instagram item was found through Meta Graph API but did not expose an analyzable caption. Upload a screenshot to check visible text."
                )
            result = _result(
                "Instagram", url, caption, item.get("username"),
                item.get("media_product_type") or item.get("media_type"),
                item.get("timestamp"),
                f"Instagram Graph API {graph_version} (authorized professional account)",
                item.get("thumbnail_url"),
            )
            result.update({
                "official_api_access_used": True,
                "official_api_provider": f"Instagram Graph API {graph_version}",
                "official_api_note": "The submitted URL matched media exposed by the configured authorized Instagram professional account.",
            })
            return result
        cursors = ((payload.get("paging") or {}).get("cursors") or {})
        after = cursors.get("after")
        if not after or not (payload.get("paging") or {}).get("next"):
            break
    raise SocialContentUnavailableError(
        "This Instagram URL was not found in the authorized professional account's accessible media. Arbitrary public-post access requires an approved Meta product with permitted use; upload a screenshot or paste the caption instead."
    )


async def _reddit(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get(
        "https://www.reddit.com/oembed", params={"url": url},
        headers={"User-Agent": "TruthScanAI/1.0 social link verifier"},
    )
    response.raise_for_status()
    data = response.json()
    return _result(
        "Reddit", url, data.get("title", ""), data.get("author_name"),
        _plain(data.get("html")), None, "Reddit oEmbed (live public metadata)",
        data.get("thumbnail_url"),
    )


async def resolve_social_url(
    url: str,
    youtube_api_key: str,
    gemini_api_key: str,
    gemini_model: str,
    x_bearer_token: str,
    meta_access_token: str,
    meta_graph_version: str,
    meta_instagram_account_id: str,
    timeout: int,
) -> dict[str, Any] | None:
    platform = platform_for_url(url)
    if not platform:
        return None
    if platform in {"Instagram", "Facebook"} and not meta_access_token:
        # Do not scrape login pages or repurpose Meta oEmbed responses for
        # analysis. Only reviewed Graph API access is used for Meta content.
        raise SocialContentUnavailableError(
            f"{platform} API access is not configured. Upload a screenshot or paste the caption, or configure a Meta token with the required approved permissions."
        )
    headers = {"User-Agent": "TruthScanAI/1.0 social link verifier"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        try:
            if platform == "YouTube":
                result = await _youtube(client, url, youtube_api_key)
            elif platform == "TikTok":
                result = await _tiktok(client, url)
            elif platform == "X":
                result = await _x(client, url, x_bearer_token)
            elif platform == "Facebook":
                result = await _facebook_graph(
                    client, url, meta_access_token, meta_graph_version
                )
            elif platform == "Instagram":
                result = await _instagram_graph(
                    client,
                    url,
                    meta_access_token,
                    meta_graph_version,
                    meta_instagram_account_id,
                )
            elif platform == "Reddit":
                result = await _reddit(client, url)
            else:
                return None
        except (httpx.HTTPError, ValueError) as exc:
            raise SocialContentUnavailableError(
                f"The public {platform} post could not be read. It may be private, deleted, age-restricted, embedding-disabled, or blocked in this region."
            ) from exc
    if platform == "YouTube":
        if gemini_api_key:
            try:
                result.update(await _youtube_video_analysis(url, gemini_api_key, gemini_model))
            except VideoAnalysisUnavailableError as exc:
                result["content_analysis_error"] = str(exc)
            except httpx.TimeoutException:
                result["content_analysis_error"] = (
                    "Gemini video processing timed out. Longer videos can require background processing; retry, use a shorter public clip, or paste the transcript."
                )
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in {401, 403}:
                    detail = "Gemini rejected the configured credential or it lacks access to video understanding."
                elif status == 429:
                    detail = "Gemini video-analysis quota or rate limit was reached. Retry later or review the Google project quota."
                elif status == 400:
                    detail = "Gemini rejected this video. It may be private, unlisted, age-restricted, region-blocked, or in an unsupported form."
                elif status >= 500:
                    detail = "Gemini's video service returned a temporary server error. Retry this request later."
                else:
                    detail = f"Gemini video analysis failed with HTTP {status}."
                result["content_analysis_error"] = detail
            except (httpx.HTTPError, ValueError, KeyError, IndexError):
                # Metadata still remains usable, but never imply audiovisual
                # checks completed when model output could not be parsed.
                result["content_analysis_error"] = (
                    "Gemini returned an unusable video-analysis response. Retry or use a shorter public clip."
                )
        else:
            result["content_analysis_error"] = (
                "GEMINI_API_KEY is not configured, so the video's spoken audio and frames were not analyzed."
            )
    if len(result.get("title") or "") < 5:
        raise SocialContentUnavailableError(
            f"The {platform} link resolved, but it did not expose enough caption or title text to verify. Upload a screenshot or paste the claim."
        )
    return result
