from __future__ import annotations

import asyncio
import secrets
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import Cookie, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from .auth import (
    clean_name,
    hash_password,
    new_session_token,
    normalize_email,
    session_token_hash,
    verify_password,
)
from .config import PROJECT_DIR, settings
from .database import NewsRepository
from .mailer import email_delivery_configured, send_plain_email
from .models import (
    Article,
    AuthResponse,
    EmailRequest,
    HealthResponse,
    LoginRequest,
    NewsMeta,
    NewsResponse,
    RefreshResponse,
    ResetPasswordRequest,
    SignupRequest,
    SourcesResponse,
    SourceStatus,
    UserPublic,
    VerificationRequest,
    VerifyEmailRequest,
    VerificationResponse,
)
from .provenance import feed_verdict
from .recency import LATEST_RUMOUR_DAYS, is_recent_rumour
from .service import NewsService
from .social import SocialContentUnavailableError
from .verification import (
    MAX_IMAGE_BYTES,
    OCRUnavailableError,
    VerificationInputError,
    VerificationService,
    image_ocr,
)

VERSION = "1.5.0"
repository = NewsRepository(settings.database_path)
news_service = NewsService(repository, settings)
verification_service = VerificationService(news_service)
verification_jobs: dict[str, dict[str, Any]] = {}
verification_job_tasks: set[asyncio.Task[Any]] = set()
SESSION_COOKIE = "truthscan_session"
SESSION_DAYS = 30

app = FastAPI(
    title="TRUTHSCAN AI API",
    description="Live news aggregation backend for the TRUTHSCAN AI prototype.",
    version=VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Key"],
)


def _article(row: dict) -> Article:
    enriched = dict(row)
    verdict, reason = feed_verdict(enriched)
    enriched["feed_verdict"] = verdict
    enriched["feed_verdict_reason"] = reason
    return Article.model_validate(enriched)


@app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    try:
        count = repository.count()
        db_status = "connected"
        status = "ok"
    except Exception:
        count = 0
        db_status = "error"
        status = "degraded"
    return HealthResponse(
        status=status,
        service="truthscan-api",
        version=VERSION,
        database=db_status,
        cached_articles=count,
        enabled_providers=news_service.enabled_providers(),
        timestamp=datetime.now(UTC),
    )


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_DAYS * 86_400,
        httponly=True,
        secure=settings.environment.casefold() == "production",
        samesite="lax",
        path="/",
    )


def _public_user(user: dict[str, Any]) -> UserPublic:
    return UserPublic.model_validate(
        {key: user[key] for key in ("id", "name", "email", "email_verified", "created_at")}
    )


def _issue_session(response: Response, user_id: str) -> None:
    now = datetime.now(UTC)
    token, token_hash = new_session_token()
    repository.create_session(
        token_hash,
        user_id,
        now.isoformat(),
        (now + timedelta(days=SESSION_DAYS)).isoformat(),
    )
    _set_session_cookie(response, token)


def _rate_limit(
    request: Request,
    bucket: str,
    identity: str,
    limit: int,
    window_seconds: int,
    block_seconds: int,
) -> str:
    host = request.client.host if request.client else "unknown"
    key_hash = session_token_hash(f"{host}|{identity.casefold()}")
    allowed, retry_after = repository.consume_rate_limit(
        bucket, key_hash, int(time.time()), limit, window_seconds, block_seconds
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many authentication attempts. Try again later.",
            headers={"Retry-After": str(max(1, retry_after))},
        )
    return key_hash


def _base_url(request: Request) -> str:
    configured = settings.app_base_url.rstrip("/")
    if settings.environment.casefold() == "production" or "localhost" not in configured:
        return configured
    return str(request.base_url).rstrip("/")


def _create_action_token(user_id: str, purpose: str, minutes: int) -> str:
    token, token_hash = new_session_token()
    now = datetime.now(UTC)
    repository.create_auth_token(
        token_hash,
        user_id,
        purpose,
        now.isoformat(),
        (now + timedelta(minutes=minutes)).isoformat(),
    )
    return token


def _send_verification(user: dict[str, Any], request: Request) -> tuple[bool, str | None]:
    token = _create_action_token(user["id"], "email_verification", 24 * 60)
    url = f"{_base_url(request)}/?verify_email={token}"
    sent = False
    try:
        sent = send_plain_email(
            settings,
            user["email"],
            "Verify your TRUTHSCAN email",
            f"Hello {user['name']},\n\nVerify your email by opening this one-time link:\n{url}\n\nThe link expires in 24 hours.",
        )
    except Exception:
        sent = False
    development_url = url if settings.environment.casefold() == "development" else None
    return sent, development_url


@app.get("/api/v1/auth/providers", tags=["accounts"])
def auth_providers() -> dict[str, Any]:
    return {
        "google": {"enabled": bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)},
        "meta": {"enabled": bool(settings.meta_oauth_app_id and settings.meta_oauth_app_secret)},
        "email_delivery": {"enabled": email_delivery_configured(settings)},
        "development_links": settings.environment.casefold() == "development",
    }


@app.post("/api/v1/auth/signup", response_model=AuthResponse, tags=["accounts"])
def signup(
    payload: SignupRequest,
    response: Response,
    http_request: Request,
) -> AuthResponse:
    try:
        name = clean_name(payload.name)
        email = normalize_email(payload.email)
        password_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _rate_limit(http_request, "signup", email, 5, 3_600, 3_600)
    created_at = datetime.now(UTC)
    user_id = uuid4().hex
    try:
        user = repository.create_user(
            user_id, name, email, password_hash, created_at.isoformat(), False
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists. Sign in instead.",
        ) from exc
    _issue_session(response, user_id)
    sent, action_url = _send_verification(user, http_request)
    if sent:
        message = "Account created. Check your email to verify the address."
    elif action_url:
        message = "Account created. Email delivery is unavailable; use the development verification link."
    else:
        message = "Account created. Verification email could not be delivered; use Resend after email delivery is configured."
    return AuthResponse(
        user=_public_user(user),
        message=message,
        action_url=action_url,
        requires_email_verification=True,
    )


@app.post("/api/v1/auth/login", response_model=AuthResponse, tags=["accounts"])
def login(
    payload: LoginRequest,
    response: Response,
    http_request: Request,
) -> AuthResponse:
    try:
        email = normalize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rate_key = _rate_limit(http_request, "login", email, 10, 900, 900)
    user = repository.user_by_email(email)
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    repository.clear_rate_limit("login", rate_key)
    _issue_session(response, user["id"])
    return AuthResponse(
        user=_public_user(user),
        message="Signed in successfully.",
        requires_email_verification=not bool(user.get("email_verified")),
    )


@app.get("/api/v1/auth/me", response_model=UserPublic, tags=["accounts"])
def current_user(
    truthscan_session: str | None = Cookie(default=None),
) -> UserPublic:
    if not truthscan_session:
        raise HTTPException(status_code=401, detail="Not signed in")
    user = repository.user_by_session(
        session_token_hash(truthscan_session), datetime.now(UTC).isoformat()
    )
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return _public_user(user)


@app.post("/api/v1/auth/verify-email", response_model=AuthResponse, tags=["accounts"])
def verify_email(payload: VerifyEmailRequest, response: Response) -> AuthResponse:
    now = datetime.now(UTC).isoformat()
    user = repository.consume_auth_token(
        session_token_hash(payload.token), "email_verification", now
    )
    if not user:
        raise HTTPException(status_code=400, detail="Verification link is invalid or expired.")
    repository.mark_email_verified(user["id"])
    user["email_verified"] = 1
    _issue_session(response, user["id"])
    return AuthResponse(
        user=_public_user(user),
        message="Email verified successfully.",
        requires_email_verification=False,
    )


@app.post("/api/v1/auth/resend-verification", tags=["accounts"])
def resend_verification(
    payload: EmailRequest,
    http_request: Request,
) -> dict[str, Any]:
    try:
        email = normalize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _rate_limit(http_request, "resend_verification", email, 4, 3_600, 3_600)
    user = repository.user_by_email(email)
    action_url = None
    if user and not user.get("email_verified"):
        _, action_url = _send_verification(user, http_request)
    return {
        "message": "If the account exists and is unverified, a new verification link has been prepared.",
        "action_url": action_url,
    }


@app.post("/api/v1/auth/forgot-password", tags=["accounts"])
def forgot_password(
    payload: EmailRequest,
    http_request: Request,
) -> dict[str, Any]:
    try:
        email = normalize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _rate_limit(http_request, "forgot_password", email, 5, 3_600, 3_600)
    user = repository.user_by_email(email)
    action_url = None
    if user:
        token = _create_action_token(user["id"], "password_reset", 30)
        url = f"{_base_url(http_request)}/?reset_password={token}"
        try:
            send_plain_email(
                settings,
                user["email"],
                "Reset your TRUTHSCAN password",
                f"Hello {user['name']},\n\nReset your password using this one-time link:\n{url}\n\nThe link expires in 30 minutes. If you did not request this, ignore the email.",
            )
        except Exception:
            pass
        if settings.environment.casefold() == "development":
            action_url = url
    return {
        "message": "If an account exists for that email, a password-reset link has been prepared.",
        "action_url": action_url,
    }


@app.post("/api/v1/auth/reset-password", tags=["accounts"])
def reset_password(
    payload: ResetPasswordRequest,
    http_request: Request,
) -> dict[str, str]:
    _rate_limit(http_request, "reset_password", payload.token, 8, 900, 900)
    user = repository.consume_auth_token(
        session_token_hash(payload.token),
        "password_reset",
        datetime.now(UTC).isoformat(),
    )
    if not user:
        raise HTTPException(status_code=400, detail="Password-reset link is invalid or expired.")
    try:
        password_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    repository.update_password(user["id"], password_hash)
    return {"message": "Password reset successfully. Sign in with the new password."}


@app.post("/api/v1/auth/logout", tags=["accounts"])
def logout(
    response: Response,
    truthscan_session: str | None = Cookie(default=None),
) -> dict[str, str]:
    if truthscan_session:
        repository.delete_session(session_token_hash(truthscan_session))
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")
    return {"message": "Signed out"}


def _oauth_redirect_uri(request: Request, provider: str) -> str:
    return f"{_base_url(request)}/api/v1/auth/oauth/{provider}/callback"


def _oauth_start_response(request: Request, provider: str) -> RedirectResponse:
    if provider == "google":
        if not (settings.google_oauth_client_id and settings.google_oauth_client_secret):
            raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
        query = urlencode({
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": _oauth_redirect_uri(request, provider),
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "online",
            "prompt": "select_account",
        })
        authorize_url = f"https://accounts.google.com/o/oauth2/v2/auth?{query}"
    elif provider == "meta":
        if not (settings.meta_oauth_app_id and settings.meta_oauth_app_secret):
            raise HTTPException(status_code=503, detail="Meta sign-in is not configured.")
        query = urlencode({
            "client_id": settings.meta_oauth_app_id,
            "redirect_uri": _oauth_redirect_uri(request, provider),
            "response_type": "code",
            "scope": "email,public_profile",
        })
        authorize_url = f"https://www.facebook.com/{settings.meta_graph_version}/dialog/oauth?{query}"
    else:
        raise HTTPException(status_code=404, detail="Unknown OAuth provider")
    state, state_hash = new_session_token()
    repository.create_oauth_state(
        state_hash,
        provider,
        (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
    )
    separator = "&" if "?" in authorize_url else "?"
    response = RedirectResponse(f"{authorize_url}{separator}state={state}", status_code=302)
    response.set_cookie(
        "truthscan_oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=settings.environment.casefold() == "production",
        samesite="lax",
        path="/api/v1/auth/oauth",
    )
    return response


@app.get("/api/v1/auth/oauth/{provider}/start", tags=["accounts"])
def oauth_start(provider: Literal["google", "meta"], request: Request) -> RedirectResponse:
    _rate_limit(request, f"oauth_{provider}", provider, 20, 900, 900)
    return _oauth_start_response(request, provider)


def _oauth_user(provider: str, subject: str, name: str, email: str) -> dict[str, Any]:
    existing = repository.user_by_oauth(provider, subject)
    if existing:
        return existing
    normalized = normalize_email(email)
    existing = repository.user_by_email(normalized)
    now = datetime.now(UTC).isoformat()
    if existing:
        repository.mark_email_verified(existing["id"])
        repository.link_oauth_account(provider, subject, existing["id"], now)
        existing["email_verified"] = 1
        return existing
    display_name = name.strip() or normalized.split("@", 1)[0]
    if len(display_name) < 2:
        display_name = "TRUTHSCAN user"
    user = repository.create_user(
        uuid4().hex,
        clean_name(display_name),
        normalized,
        "!oauth-only",
        now,
        True,
    )
    repository.link_oauth_account(provider, subject, user["id"], now)
    return user


async def _oauth_callback_impl(
    provider: str,
    request: Request,
    code: str,
    state: str,
    state_cookie: str | None,
) -> RedirectResponse:
    if not state_cookie or not secrets.compare_digest(state, state_cookie):
        return RedirectResponse("/?auth_error=oauth_state", status_code=302)
    if not repository.consume_oauth_state(
        session_token_hash(state), provider, datetime.now(UTC).isoformat()
    ):
        return RedirectResponse("/?auth_error=oauth_expired", status_code=302)
    redirect_uri = _oauth_redirect_uri(request, provider)
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            if provider == "google":
                token_response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "code": code,
                        "client_id": settings.google_oauth_client_id,
                        "client_secret": settings.google_oauth_client_secret,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
                token_response.raise_for_status()
                access_token = token_response.json().get("access_token")
                profile_response = await client.get(
                    "https://openidconnect.googleapis.com/v1/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            else:
                token_response = await client.get(
                    f"https://graph.facebook.com/{settings.meta_graph_version}/oauth/access_token",
                    params={
                        "client_id": settings.meta_oauth_app_id,
                        "client_secret": settings.meta_oauth_app_secret,
                        "redirect_uri": redirect_uri,
                        "code": code,
                    },
                )
                token_response.raise_for_status()
                access_token = token_response.json().get("access_token")
                profile_response = await client.get(
                    f"https://graph.facebook.com/{settings.meta_graph_version}/me",
                    params={"fields": "id,name,email"},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            profile_response.raise_for_status()
            profile = profile_response.json()
        subject = str(profile.get("sub") or profile.get("id") or "")
        email = str(profile.get("email") or "")
        name = str(profile.get("name") or "")
        if provider == "google" and profile.get("email_verified") is not True:
            raise ValueError("Google did not return a verified email")
        if not subject or not email:
            raise ValueError("OAuth provider did not return a usable email identity")
        user = _oauth_user(provider, subject, name, email)
    except Exception:
        return RedirectResponse("/?auth_error=oauth_failed", status_code=302)
    response = RedirectResponse("/?auth=success", status_code=302)
    _issue_session(response, user["id"])
    response.delete_cookie("truthscan_oauth_state", path="/api/v1/auth/oauth")
    return response


@app.get("/api/v1/auth/oauth/google/callback", tags=["accounts"])
async def google_oauth_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    truthscan_oauth_state: str | None = Cookie(default=None),
) -> RedirectResponse:
    if error or not code or not state:
        return RedirectResponse("/?auth_error=oauth_failed", status_code=302)
    return await _oauth_callback_impl("google", request, code, state, truthscan_oauth_state)


@app.get("/api/v1/auth/oauth/meta/callback", tags=["accounts"])
async def meta_oauth_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    truthscan_oauth_state: str | None = Cookie(default=None),
) -> RedirectResponse:
    if error or not code or not state:
        return RedirectResponse("/?auth_error=oauth_failed", status_code=302)
    return await _oauth_callback_impl("meta", request, code, state, truthscan_oauth_state)


@app.get("/api/v1/sources", response_model=SourcesResponse, tags=["news"])
def sources() -> SourcesResponse:
    items = [SourceStatus.model_validate(item) for item in news_service.source_status()]
    return SourcesResponse(sources=items, count=len(items))


@app.get("/api/v1/news", response_model=NewsResponse, tags=["news"])
async def list_news(
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=40),
    sort: Literal["newest", "trending", "relevant"] = "newest",
    limit: int = Query(default=40, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
) -> NewsResponse:
    rows, refresh = await news_service.list_articles(
        query=q, category=category, sort=sort, limit=limit, offset=offset
    )
    refreshed_at = refresh.get("refreshed_at")
    return NewsResponse(
        articles=[_article(row) for row in rows],
        meta=NewsMeta(
            count=len(rows),
            query=q,
            category=category,
            sort=sort,
            live=True,
            cached=bool(refresh.get("cached")),
            refreshed_at=refreshed_at,
            warnings=refresh.get("warnings", [])[:5],
            best_count=sum(1 for row in rows if row.get("match_type") == "best"),
            related_count=sum(1 for row in rows if row.get("match_type") == "related"),
        ),
    )


@app.get("/api/v1/news/trending", response_model=NewsResponse, tags=["news"])
async def trending_news(
    category: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=20, ge=1, le=100),
) -> NewsResponse:
    rows, refresh = await news_service.list_articles(
        query=None, category=category, sort="trending", limit=limit, offset=0
    )
    return NewsResponse(
        articles=[_article(row) for row in rows],
        meta=NewsMeta(
            count=len(rows), category=category, sort="trending", live=True,
            cached=bool(refresh.get("cached")),
            refreshed_at=refresh.get("refreshed_at"),
            warnings=refresh.get("warnings", [])[:5],
        ),
    )


@app.get("/api/v1/rumours", response_model=NewsResponse, tags=["fact-checks"])
async def recent_rumours(
    limit: int = Query(default=60, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
) -> NewsResponse:
    # Fetch a larger newest-first window, then apply the strict publication
    # cutoff before pagination. Fetched-at time is deliberately not used as a
    # substitute because rediscovering an old URL does not make its rumour new.
    candidates, refresh = await news_service.list_articles(
        query=None,
        category="Fact Check",
        sort="newest",
        limit=min(1_000, max(300, offset + limit)),
        offset=0,
    )
    recent = [
        row for row in candidates if is_recent_rumour(row.get("published_at"))
    ]
    rows = recent[offset : offset + limit]
    return NewsResponse(
        articles=[_article(row) for row in rows],
        meta=NewsMeta(
            count=len(rows),
            category="Fact Check",
            sort="newest",
            live=True,
            cached=bool(refresh.get("cached")),
            refreshed_at=refresh.get("refreshed_at"),
            warnings=refresh.get("warnings", [])[:10],
            recency_days=LATEST_RUMOUR_DAYS,
        ),
    )


@app.post("/api/v1/rumours/refresh", response_model=RefreshResponse, tags=["fact-checks"])
async def refresh_rumours() -> RefreshResponse:
    result = await news_service.refresh(category="Fact Check", force=True)
    return RefreshResponse(
        fetched=result["fetched"],
        stored=result["stored"],
        new_items=result.get("new_items", 0),
        updated_items=result.get("updated_items", 0),
        warnings=result["warnings"],
        refreshed_at=result["refreshed_at"],
    )


@app.get("/api/v1/news/{article_id}", response_model=Article, tags=["news"])
def article_detail(article_id: str) -> Article:
    row = repository.get(article_id)
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")
    return _article(row)


async def _verify_text_request(request: VerificationRequest) -> VerificationResponse:
    try:
        result = await verification_service.verify(
            text=request.source_url or request.text,
            input_type="text",
            extracted_text=request.text if request.source_url else None,
            extraction_method="Submitted text" if not request.source_url else "Public page title",
        )
        return VerificationResponse.model_validate(result)
    except VerificationInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SocialContentUnavailableError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (httpx.HTTPError, OSError) as exc:
        raise HTTPException(
            status_code=422,
            detail="The supplied URL could not be read. Paste its headline or claim instead.",
        ) from exc


@app.post("/api/v1/verify/text", response_model=VerificationResponse, tags=["verification"])
async def verify_text(request: VerificationRequest) -> VerificationResponse:
    return await _verify_text_request(request)


async def _run_verification_job(job_id: str, request: VerificationRequest) -> None:
    job = verification_jobs[job_id]
    job["status"] = "running"
    job["stage"] = "Retrieving the post and analyzing available content"
    try:
        response = await _verify_text_request(request)
        job["status"] = "completed"
        job["stage"] = "Completed"
        job["result"] = response.model_dump(mode="json")
    except HTTPException as exc:
        job["status"] = "failed"
        job["stage"] = "Failed"
        job["error"] = str(exc.detail)
        job["http_status"] = exc.status_code
    except Exception:
        job["status"] = "failed"
        job["stage"] = "Failed"
        job["error"] = "Verification failed unexpectedly. Retry the request."
        job["http_status"] = 500
    finally:
        job["updated_at"] = datetime.now(UTC).isoformat()


def _prune_verification_jobs() -> None:
    cutoff = time.time() - 3_600
    stale = [
        job_id for job_id, job in verification_jobs.items()
        if job.get("created_epoch", 0) < cutoff and job.get("status") in {"completed", "failed"}
    ]
    for job_id in stale:
        verification_jobs.pop(job_id, None)


@app.post("/api/v1/verify/jobs", tags=["verification"])
async def create_verification_job(request: VerificationRequest) -> dict[str, Any]:
    _prune_verification_jobs()
    job_id = uuid4().hex
    verification_jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "stage": "Queued",
        "result": None,
        "error": None,
        "http_status": None,
        "created_epoch": time.time(),
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    task = asyncio.create_task(_run_verification_job(job_id, request))
    verification_job_tasks.add(task)
    task.add_done_callback(verification_job_tasks.discard)
    return {"id": job_id, "status": "queued", "stage": "Queued"}


@app.get("/api/v1/verify/jobs/{job_id}", tags=["verification"])
async def get_verification_job(job_id: str) -> dict[str, Any]:
    job = verification_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Verification job not found or expired")
    return {key: value for key, value in job.items() if key != "created_epoch"}


@app.post(
    "/api/v1/verify/article/{article_id}",
    response_model=VerificationResponse,
    tags=["verification"],
)
async def verify_article(article_id: str) -> VerificationResponse:
    row = repository.get(article_id)
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")
    # Use the headline as the search claim; a longer feed description can
    # otherwise overpower it during claim selection. Preserve the original
    # article as guaranteed provenance in the report.
    result = await verification_service.verify(
        text=row["headline"],
        input_type="article",
        seed_article=row,
    )
    return VerificationResponse.model_validate(result)


@app.post("/api/v1/verify/image", response_model=VerificationResponse, tags=["verification"])
async def verify_image(
    image: UploadFile = File(...),
    claim: str = Form(default="", max_length=2_000),
) -> VerificationResponse:
    if image.content_type and not image.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Upload a PNG, JPEG, WebP, TIFF, or BMP image.")
    content = await image.read(MAX_IMAGE_BYTES + 1)
    try:
        extracted, method = image_ocr(content, image.filename)
    except OCRUnavailableError as exc:
        if not claim.strip():
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        extracted, method = "", "Manual headline fallback"
    except VerificationInputError as exc:
        if not claim.strip():
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        extracted, method = "", "Manual headline fallback"
    text = claim.strip() or extracted
    try:
        result = await verification_service.verify(
            text=text,
            input_type="image",
            extracted_text=extracted or claim.strip(),
            extraction_method=method,
        )
        return VerificationResponse.model_validate(result)
    except VerificationInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/news/refresh", response_model=RefreshResponse, tags=["news"])
async def refresh_news(
    x_admin_key: str | None = Header(default=None),
) -> RefreshResponse:
    if settings.admin_key and x_admin_key != settings.admin_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")
    result = await news_service.refresh(force=True)
    return RefreshResponse(
        fetched=result["fetched"],
        stored=result["stored"],
        new_items=result.get("new_items", 0),
        updated_items=result.get("updated_items", 0),
        warnings=result["warnings"],
        refreshed_at=result["refreshed_at"],
    )


# Serve the existing frontend and API from one origin. This keeps API keys on
# the server and avoids browser CORS/proxy problems in local and hosted use.
ASSETS = {"index.html", "styles.css", "data.js", "app.js"}


@app.get("/", include_in_schema=False)
def frontend_index() -> FileResponse:
    return FileResponse(PROJECT_DIR / "index.html")


@app.get("/{asset_path:path}", include_in_schema=False)
def frontend_assets(asset_path: str) -> FileResponse:
    if asset_path in ASSETS:
        path = PROJECT_DIR / asset_path
        if path.is_file():
            return FileResponse(path)
    # The UI is a client-side SPA; unknown non-API paths return the shell.
    if not asset_path.startswith("api/"):
        return FileResponse(PROJECT_DIR / "index.html")
    raise HTTPException(status_code=404, detail="Not found")
