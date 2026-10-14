from __future__ import annotations

import asyncio
import html
import ipaddress
import re
import shutil
import socket
import subprocess
import tempfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image, UnidentifiedImageError

from .factchecks import FACT_CHECKER_NAMES, rating_kind, search_fact_checks
from .provenance import recognized_publisher as _recognized_publisher
from .service import NewsService
from .social import SocialContentUnavailableError, resolve_social_url

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 30_000_000
SUSPICIOUS_PHRASES = (
    "share immediately",
    "forward this",
    "they don't want you to know",
    "media won't show",
    "100% true",
    "shocking truth",
    "urgent warning",
    "before it is deleted",
    "you won't believe",
)
UI_LINES = {
    "like", "comment", "share", "follow", "following", "subscribe",
    "home", "reels", "notifications", "send message", "sponsored",
}

class VerificationInputError(ValueError):
    pass


class OCRUnavailableError(RuntimeError):
    pass


def _public_host(hostname: str) -> bool:
    try:
        addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for item in addresses:
        address = ipaddress.ip_address(item[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            return False
    return bool(addresses)


def _safe_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and _public_host(parsed.hostname)
    except (ValueError, UnicodeError):
        return False


async def title_from_url(url: str, timeout: int = 10) -> str | None:
    """Read only public HTML metadata with redirect-by-redirect SSRF checks."""
    current = url
    headers = {"User-Agent": "TruthScanAI/1.0 (verification metadata fetch)"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=False) as client:
        for _ in range(4):
            if not _safe_http_url(current):
                raise VerificationInputError("Only public http/https news links are accepted.")
            async with client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        return None
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type:
                    return None
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 600_000:
                        break
                    chunks.append(chunk)
                markup = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                patterns = (
                    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
                    r"<title[^>]*>(.*?)</title>",
                )
                for pattern in patterns:
                    match = re.search(pattern, markup, flags=re.I | re.S)
                    if match:
                        title = re.sub(r"\s+", " ", html.unescape(match.group(1))).strip()
                        if len(title) >= 5:
                            return title[:400]
                return None
    return None


def _clean_text(value: str) -> str:
    value = value.replace("\x00", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()[:8_000]


def select_claim(text: str) -> str:
    """Select a searchable headline/claim from pasted text or OCR output."""
    cleaned = _clean_text(text)
    if not cleaned:
        raise VerificationInputError("No readable news text was supplied.")
    if re.fullmatch(r"https?://\S+", cleaned, flags=re.I):
        return cleaned

    lines = [re.sub(r"\s+", " ", line).strip(" -|•") for line in cleaned.splitlines()]
    candidates: list[tuple[float, str]] = []
    for line in lines:
        lower = line.casefold()
        words = re.findall(r"[^\W_]+", line, flags=re.UNICODE)
        letters = sum(char.isalpha() for char in line)
        if len(line) < 12 or len(words) < 3 or lower in UI_LINES:
            continue
        if letters / max(1, len(line)) < 0.45:
            continue
        length_score = min(len(line), 160) / 4
        word_score = min(len(words), 22) * 2
        punctuation_penalty = max(0, len(line) - 220) / 5
        candidates.append((length_score + word_score - punctuation_penalty, line))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1][:300]

    sentence = re.split(r"(?<=[.!?])\s+", cleaned)[0]
    return sentence[:300]


def image_ocr(content: bytes, filename: str | None = None) -> tuple[str, str]:
    if not content:
        raise VerificationInputError("The uploaded image is empty.")
    if len(content) > MAX_IMAGE_BYTES:
        raise VerificationInputError("Image is larger than the 10 MB limit.")
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise VerificationInputError("Image dimensions are too large.")
            image = source.convert("RGB")
            # Upscale small screenshots for materially better OCR.
            if image.width < 1400:
                ratio = min(2.0, 1400 / max(1, image.width))
                image = image.resize((int(image.width * ratio), int(image.height * ratio)))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise VerificationInputError("Unsupported or invalid image file.") from exc

    executable = shutil.which("tesseract")
    if not executable:
        raise OCRUnavailableError(
            "Server OCR is not installed. Add Tesseract OCR or type the headline shown in the screenshot."
        )
    suffix = Path(filename or "upload.png").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}:
        suffix = ".png"
    try:
        language_probe = subprocess.run(
            [executable, "--list-langs"], capture_output=True, text=True, timeout=5
        )
        installed_languages = set(language_probe.stdout.splitlines())
    except (OSError, subprocess.TimeoutExpired):
        installed_languages = {"eng"}
    ocr_languages = "eng+hin" if "hin" in installed_languages else "eng"
    with tempfile.TemporaryDirectory(prefix="truthscan-") as folder:
        path = Path(folder) / f"image{suffix}"
        image.save(path)
        try:
            process = subprocess.run(
                [executable, str(path), "stdout", "-l", ocr_languages, "--psm", "6"],
                capture_output=True,
                text=True,
                timeout=25,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OCRUnavailableError("OCR timed out while reading the screenshot.") from exc
        text = _clean_text(process.stdout)
        if process.returncode != 0 or len(text) < 8:
            raise VerificationInputError(
                "No readable news text was detected. Try a clearer crop or type the headline manually."
            )
        language_label = "English + Hindi" if "hin" in installed_languages else "English"
        return text, f"Local Tesseract OCR ({language_label})"


class VerificationService:
    def __init__(self, news_service: NewsService):
        self.news_service = news_service

    async def verify(
        self,
        text: str,
        input_type: str,
        extracted_text: str | None = None,
        extraction_method: str | None = None,
        seed_article: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raw = _clean_text(text)
        social_context: dict[str, Any] | None = None
        query_override: str | None = None
        if re.fullmatch(r"https?://\S+", raw, flags=re.I):
            social_context = await resolve_social_url(
                raw,
                youtube_api_key=self.news_service.settings.youtube_api_key,
                gemini_api_key=self.news_service.settings.gemini_api_key,
                gemini_model=self.news_service.settings.gemini_model,
                x_bearer_token=self.news_service.settings.x_bearer_token,
                meta_access_token=self.news_service.settings.meta_access_token,
                meta_graph_version=self.news_service.settings.meta_graph_version,
                meta_instagram_account_id=self.news_service.settings.meta_instagram_account_id,
                timeout=self.news_service.settings.request_timeout_seconds,
            )
            if social_context:
                input_type = "social"
                extracted_claims = social_context.get("extracted_claims") or []
                query_override = extracted_claims[0] if extracted_claims else social_context["title"]
                raw = "\n".join(
                    value for value in (
                        *extracted_claims,
                        social_context.get("content_summary"),
                        social_context.get("title"),
                        social_context.get("description"),
                    ) if value
                )
                extraction_method = social_context.get("resolver")
                if social_context.get("audiovisual_content_analyzed"):
                    extraction_method = (
                        f"{extraction_method}; {social_context.get('content_analysis_provider')}"
                    )
                extracted_text = raw
            else:
                title = await title_from_url(raw, self.news_service.settings.request_timeout_seconds)
                if title:
                    raw = title
        query = select_claim(query_override or raw)
        (news_result, fact_result) = await asyncio.gather(
            self.news_service.list_articles(
                query=query,
                category=None,
                sort="relevant",
                limit=30,
                offset=0,
            ),
            search_fact_checks(
                query=query,
                api_key=self.news_service.settings.google_fact_check_api_key,
                timeout=self.news_service.settings.request_timeout_seconds,
            ),
        )
        rows, _ = news_result
        if seed_article:
            original = dict(seed_article)
            original["relevance_score"] = 100.0
            original["match_type"] = "best"
            rows = [original, *[row for row in rows if row.get("id") != original.get("id")]]
        discovered_checks, _fact_warnings = fact_result
        fact_checks: list[dict[str, Any]] = []
        for review in discovered_checks:
            match_score = self.news_service._score_article(
                query,
                {
                    "headline": review.get("claim_text") or review.get("title") or "",
                    "description": "",
                    "source": review.get("publisher") or "",
                    "is_trending": False,
                },
            )
            review["_match_score"] = match_score
            if review.get("structured") or match_score >= 18:
                fact_checks.append(review)
        # Search and verification views display the closest matching reviews
        # first. Structured ClaimReview records win ties, but no item is treated
        # as a debunk unless its attributed rating is explicitly negative.
        fact_checks.sort(
            key=lambda review: (
                float(review.get("_match_score") or 0),
                bool(review.get("structured")),
            ),
            reverse=True,
        )
        fact_urls = {review["url"].split("#", 1)[0].rstrip("/") for review in fact_checks}
        reported_by = [
            row for row in rows
            if float(row.get("relevance_score") or 0) >= 18
            and str(row.get("url") or "").split("#", 1)[0].rstrip("/") not in fact_urls
            and not any(name in str(row.get("source") or "").casefold() for name in FACT_CHECKER_NAMES)
            and "fact check" not in str(row.get("headline") or "").casefold()
        ]
        # One row per publisher makes the provenance section easier to audit.
        # Mark allowlisted publishers explicitly so a one-source supported
        # outcome is based on a visible, reviewable policy rather than a guess.
        unique_publishers: dict[str, dict[str, Any]] = {}
        for row in reported_by:
            row["recognized_publisher"] = _recognized_publisher(row.get("source"))
            key = str(row.get("source") or "Unknown publisher").strip().casefold()
            if key not in unique_publishers:
                unique_publishers[key] = row
        reported_by = list(unique_publishers.values())
        sources = {key for key in unique_publishers if key and key != "unknown publisher"}
        strong = [row for row in reported_by if float(row.get("relevance_score") or 0) >= 48]
        recognized_strong = [row for row in strong if row.get("recognized_publisher")]
        source_count = len(sources)

        lower = raw.casefold()
        phrase_hits = [phrase for phrase in SUSPICIOUS_PHRASES if phrase in lower]
        letters = [char for char in raw if char.isalpha()]
        caps_ratio = sum(char.isupper() for char in letters) / max(1, len(letters))
        excessive_punctuation = bool(re.search(r"[!?]{3,}", raw))
        language_flags = len(phrase_hits) + int(caps_ratio > 0.7 and len(letters) > 20) + int(excessive_punctuation)

        negative_reviews = [
            review for review in fact_checks
            if rating_kind(review["rating"]) == "negative"
            and (review.get("structured") or float(review.get("_match_score") or 0) >= 32)
        ]
        positive_reviews = [
            review for review in fact_checks
            if rating_kind(review["rating"]) == "positive"
            and (review.get("structured") or float(review.get("_match_score") or 0) >= 32)
        ]
        if negative_reviews and positive_reviews:
            verdict = "DISPUTED OR MIXED"
            summary = "Fact-checking organizations returned conflicting ratings. The reviews are shown below so their evidence and definitions can be compared directly."
            real_context = "The available fact-checkers do not agree. Open each review and compare the exact version of the claim that was assessed."
        elif negative_reviews:
            verdict = "DEBUNKED BY FACT-CHECKERS"
            first = negative_reviews[0]
            summary = f"{first['publisher']} rated the matching claim “{first['rating']}”. The debunk article and any additional reviews are linked below."
            real_context = f"{first['publisher']} explains the correction in: “{first['title']}”. Use the linked review as the attributed source for the corrected context."
        elif source_count >= 4 and len(strong) >= 2:
            verdict = "SUPPORTED BY MULTIPLE SOURCES"
            names = ", ".join(row.get("source", "Unknown") for row in reported_by[:5])
            summary = f"Closely matching reports were published independently by {names}{' and others' if source_count > 5 else ''}. Each report is linked below."
            real_context = "The central event is reported by multiple publishers. Individual details, quotations, dates, and numbers should still be checked in the linked reports or a primary source."
        elif positive_reviews and source_count >= 2:
            verdict = "SUPPORTED BY MULTIPLE SOURCES"
            summary = "A structured fact-check supports the claim and matching reports were also found from multiple publishers."
            real_context = f"The supporting fact-check is “{positive_reviews[0]['title']}” by {positive_reviews[0]['publisher']}."
        elif positive_reviews:
            verdict = "SUPPORTED BY A VERIFIED NEWS SOURCE"
            summary = f"{positive_reviews[0]['publisher']} published a supporting fact-check rating for the matching claim. No attributable debunk was found."
            real_context = f"Provisional support comes from the linked review, “{positive_reviews[0]['title']}”. A later correction or contrary fact-check should supersede this outcome."
        elif recognized_strong:
            verdict = "SUPPORTED BY A VERIFIED NEWS SOURCE"
            publisher = recognized_strong[0].get("source", "Recognized publisher")
            summary = f"A closely matching report was published by {publisher}, a publisher in TRUTHSCAN's reviewed source registry. No attributable debunk was found."
            real_context = "Under the one-source policy, this news is provisionally supported by the recognized publisher shown below. This establishes attributable reporting, while a later correction or fact-check can change the outcome."
        elif source_count >= 1:
            verdict = "REPORTED BY NAMED SOURCES — NEEDS MORE VERIFICATION"
            names = ", ".join(row.get("source", "Unknown") for row in reported_by[:4])
            summary = f"Matching coverage was found from {names}, but no strongly matching publisher from TRUTHSCAN's reviewed source registry was identified."
            real_context = "The report is attributable to the publishers listed below, but it remains outside the one-source supported policy until a recognized source or explicit fact-check matches it."
        else:
            verdict = "NO VERDICT — INSUFFICIENT EVIDENCE"
            summary = "No explicit debunk and no independently attributable matching report were found. TRUTHSCAN does not convert missing evidence into a fake/real judgement."
            real_context = None

        if negative_reviews:
            fact_status = "warning"
            fact_detail = f"{len(negative_reviews)} explicit negative rating{'s' if len(negative_reviews) != 1 else ''} found from named fact-checkers."
        elif positive_reviews:
            fact_status = "support"
            fact_detail = f"{len(positive_reviews)} supporting fact-check rating{'s' if len(positive_reviews) != 1 else ''} found."
        elif fact_checks:
            fact_status = "neutral"
            fact_detail = f"{len(fact_checks)} relevant fact-check article{'s' if len(fact_checks) != 1 else ''} found without a machine-readable rating; inspect them below."
        else:
            fact_status = "neutral"
            fact_detail = "No matching review was found in the connected fact-check sources."

        signals: list[dict[str, str]] = [
            {
                "status": fact_status,
                "title": "Published fact checks",
                "detail": fact_detail,
            },
            {
                "status": "support" if (source_count >= 4 or recognized_strong) else ("neutral" if source_count else "warning"),
                "title": "Who reported the claim",
                "detail": (
                    f"{source_count} distinct publisher{'s' if source_count != 1 else ''} were identified; {len(recognized_strong)} strongly matching publisher{'s' if len(recognized_strong) != 1 else ''} belong to TRUTHSCAN's reviewed source registry."
                ),
            },
            {
                "status": "support" if strong else ("neutral" if reported_by else "warning"),
                "title": "Claim alignment",
                "detail": f"{len(strong)} publisher report{'s' if len(strong) != 1 else ''} closely match the submitted wording.",
            },
            {
                "status": "warning" if language_flags else "neutral",
                "title": "Wording indicators — not a verdict",
                "detail": (
                    f"The submission contains {language_flags} virality or manipulation indicator{'s' if language_flags != 1 else ''}. This did not determine the verdict."
                    if language_flags else "No obvious share-bait, extreme capitalization, or repeated punctuation was detected."
                ),
            },
        ]
        checks = [
            "Structured fact-check claim search" if self.news_service.settings.google_fact_check_api_key else "Recognized fact-checker article discovery",
            "Live multi-publisher headline search",
            "Publisher attribution, reviewed-source registry check, and deduplication",
            "Exact claim and headline alignment",
            "Publication-date comparison",
        ]
        if input_type == "image":
            checks.insert(0, "Screenshot validation and OCR text extraction")
        if input_type == "social":
            if social_context and social_context.get("official_api_access_used"):
                checks.insert(
                    0,
                    f"Official {social_context.get('official_api_provider')} live content retrieval",
                )
            else:
                checks.insert(0, f"Live {social_context.get('platform') if social_context else 'social'} post metadata retrieval")
            if social_context and social_context.get("audiovisual_content_analyzed"):
                checks.insert(1, "Actual video audio and sampled-frame claim extraction")
        limitations = [
            "Only an attributed fact-check review with an explicit negative rating can trigger the debunked verdict.",
            "One strongly matching report from a publisher in TRUTHSCAN's reviewed registry now produces provisional support. It establishes attributable reporting, not permanent proof, and a later correction or debunk can supersede it.",
            "Many publishers repeating a statement does not prove every detail is correct; open the linked reports and primary documents.",
            "No verdict means insufficient evidence, not falsehood.",
            "Connected services may omit private, deleted, paywalled, local, or not-yet-indexed material.",
        ]
        if not self.news_service.settings.google_fact_check_api_key:
            limitations.append(
                "The structured Google Fact Check Tools API is not configured; fallback discovery can find fact-check articles, but some ratings may require opening the review."
            )
        if input_type == "image":
            limitations.append(
                "OCR verifies the screenshot's written claim. Reverse-image provenance, pixel manipulation, and deepfake detection require a separate forensic vision service."
            )
        if input_type == "social":
            if social_context and social_context.get("audiovisual_content_analyzed"):
                limitations.append(
                    "For this YouTube link, audio and sampled frames were analyzed to extract claims. This report searches the first/main extracted claim; additional listed claims require separate checks. Video-model extraction can miss or mishear details, so review the extracted wording and linked evidence."
                )
            else:
                limitations.append(
                    "For this social link, the live public caption/title and available description were checked. Spoken audio and video frames were not analyzed; the social-content card explains why."
                )
        return {
            "input_type": input_type,
            "query": query,
            "extracted_text": extracted_text,
            "extraction_method": extraction_method,
            "social_context": social_context,
            "verdict": verdict,
            "summary": summary,
            "source_count": source_count,
            "reported_by": reported_by[:15],
            "fact_checks": fact_checks[:12],
            "real_context": real_context,
            "signals": signals,
            "checks_performed": checks,
            "limitations": limitations,
            "analyzed_at": datetime.now(UTC),
        }
