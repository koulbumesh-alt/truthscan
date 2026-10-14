from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Article(BaseModel):
    id: str
    headline: str
    description: str = ""
    source: str
    provider: str
    author: str | None = None
    url: str
    image_url: str | None = None
    category: str = "World"
    published_at: datetime | None = None
    fetched_at: datetime
    is_trending: bool = False
    relevance_score: float | None = None
    match_type: Literal["best", "related"] | None = None
    recognized_publisher: bool = False
    feed_verdict: Literal[
        "DEBUNKED BY FACT-CHECKERS",
        "SUPPORTED BY VERIFIED NEWS SOURCE",
        "MORE VERIFICATION NEEDED",
    ] = "MORE VERIFICATION NEEDED"
    feed_verdict_reason: str = "Run an in-app evidence check for this item."


class NewsMeta(BaseModel):
    count: int
    query: str | None = None
    category: str | None = None
    sort: str
    live: bool = True
    cached: bool = False
    refreshed_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)
    best_count: int = 0
    related_count: int = 0
    recency_days: int | None = None


class NewsResponse(BaseModel):
    articles: list[Article]
    meta: NewsMeta


class SourceStatus(BaseModel):
    id: str
    name: str
    kind: Literal["rss", "api"]
    category: str
    enabled: bool
    requires_key: bool = False
    note: str | None = None


class SourcesResponse(BaseModel):
    sources: list[SourceStatus]
    count: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    database: str
    cached_articles: int
    enabled_providers: list[str]
    timestamp: datetime


class RefreshResponse(BaseModel):
    fetched: int
    stored: int
    new_items: int = 0
    updated_items: int = 0
    warnings: list[str] = Field(default_factory=list)
    refreshed_at: datetime


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class UserPublic(BaseModel):
    id: str
    name: str
    email: str
    email_verified: bool = False
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserPublic
    message: str
    action_url: str | None = None
    requires_email_verification: bool = False


class EmailRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=20, max_length=500)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20, max_length=500)
    password: str = Field(min_length=8, max_length=128)


class VerificationRequest(BaseModel):
    text: str = Field(min_length=3, max_length=8_000)
    source_url: str | None = Field(default=None, max_length=2_000)


class VerificationSignal(BaseModel):
    status: Literal["support", "warning", "neutral"]
    title: str
    detail: str


class FactCheckReview(BaseModel):
    publisher: str
    site: str | None = None
    rating: str
    title: str
    url: str
    review_date: datetime | None = None
    claim_text: str | None = None
    claimant: str | None = None
    language_code: str | None = None
    structured: bool = False


class SocialContext(BaseModel):
    platform: str
    source_url: str
    title: str
    author: str | None = None
    description: str | None = None
    published_at: datetime | None = None
    resolver: str
    thumbnail_url: str | None = None
    retrieved_at: datetime
    official_api_access_used: bool = False
    official_api_provider: str | None = None
    official_api_note: str | None = None
    audiovisual_content_analyzed: bool = False
    content_analysis_provider: str | None = None
    content_summary: str | None = None
    extracted_claims: list[str] = Field(default_factory=list)
    visible_text: list[str] = Field(default_factory=list)
    content_analysis_notes: str | None = None
    content_analysis_error: str | None = None


class VerificationResponse(BaseModel):
    input_type: Literal["text", "article", "image", "social"]
    query: str
    extracted_text: str | None = None
    extraction_method: str | None = None
    social_context: SocialContext | None = None
    verdict: Literal[
        "SUPPORTED BY MULTIPLE SOURCES",
        "SUPPORTED BY A VERIFIED NEWS SOURCE",
        "REPORTED BY NAMED SOURCES — NEEDS MORE VERIFICATION",
        "DEBUNKED BY FACT-CHECKERS",
        "DISPUTED OR MIXED",
        "NO VERDICT — INSUFFICIENT EVIDENCE",
    ]
    summary: str
    source_count: int
    reported_by: list[Article]
    fact_checks: list[FactCheckReview]
    real_context: str | None = None
    signals: list[VerificationSignal]
    checks_performed: list[str]
    limitations: list[str]
    analyzed_at: datetime
