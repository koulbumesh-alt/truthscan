from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")


def _integer(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _secret(name: str, file_name: str) -> str:
    """Read a secret from a mounted file first, then an environment variable.

    Secret-file support works with Docker/Kubernetes secrets and cloud secret
    managers that mount decrypted values only inside the running service. The
    value is deliberately never returned by an API or written to application
    logs.
    """
    secret_path = os.getenv(file_name, "").strip()
    if secret_path:
        path = Path(secret_path).expanduser()
        if not path.is_absolute():
            path = PROJECT_DIR / path
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"Configured secret file for {name} could not be read") from exc
    return os.getenv(name, "").strip()


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("TRUTHSCAN_ENV", "development")
    host: str = os.getenv("TRUTHSCAN_HOST", "0.0.0.0")
    port: int = _integer("TRUTHSCAN_PORT", 8000)
    database_path: Path = PROJECT_DIR / os.getenv(
        "TRUTHSCAN_DATABASE_PATH", "backend/data/truthscan.db"
    )
    cache_ttl_seconds: int = _integer("TRUTHSCAN_CACHE_TTL_SECONDS", 300)
    request_timeout_seconds: int = _integer("TRUTHSCAN_REQUEST_TIMEOUT_SECONDS", 12)
    max_articles_per_feed: int = _integer("TRUTHSCAN_MAX_ARTICLES_PER_FEED", 25)
    gnews_api_key: str = os.getenv("GNEWS_API_KEY", "").strip()
    newsapi_key: str = os.getenv("NEWSAPI_KEY", "").strip()
    google_fact_check_api_key: str = os.getenv("GOOGLE_FACT_CHECK_API_KEY", "").strip()
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "").strip()
    gemini_api_key: str = _secret("GEMINI_API_KEY", "GEMINI_API_KEY_FILE")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
    x_bearer_token: str = _secret("X_BEARER_TOKEN", "X_BEARER_TOKEN_FILE")
    meta_access_token: str = _secret("META_ACCESS_TOKEN", "META_ACCESS_TOKEN_FILE")
    meta_graph_version: str = os.getenv("META_GRAPH_VERSION", "v26.0").strip()
    meta_instagram_account_id: str = os.getenv("META_INSTAGRAM_ACCOUNT_ID", "").strip()
    app_base_url: str = os.getenv("TRUTHSCAN_APP_BASE_URL", "http://localhost:8000").strip().rstrip("/")
    smtp_host: str = os.getenv("SMTP_HOST", "").strip()
    smtp_port: int = _integer("SMTP_PORT", 587)
    smtp_username: str = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password: str = _secret("SMTP_PASSWORD", "SMTP_PASSWORD_FILE")
    smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", "").strip()
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").strip().casefold() not in {"0", "false", "no"}
    google_oauth_client_id: str = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    google_oauth_client_secret: str = _secret("GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_CLIENT_SECRET_FILE")
    meta_oauth_app_id: str = os.getenv("META_OAUTH_APP_ID", "").strip()
    meta_oauth_app_secret: str = _secret("META_OAUTH_APP_SECRET", "META_OAUTH_APP_SECRET_FILE")
    admin_key: str = os.getenv("TRUTHSCAN_ADMIN_KEY", "").strip()
    cors_origins: tuple[str, ...] = tuple(
        x.strip()
        for x in os.getenv(
            "TRUTHSCAN_CORS_ORIGINS",
            "http://localhost:8000,http://127.0.0.1:8000",
        ).split(",")
        if x.strip()
    )


settings = Settings()
