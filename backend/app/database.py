from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


class NewsRepository:
    """Small SQLite repository. Its public methods form the storage boundary,
    so a PostgreSQL implementation can replace it without changing API routes.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY,
                    headline TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    author TEXT,
                    url TEXT NOT NULL,
                    image_url TEXT,
                    category TEXT NOT NULL,
                    published_at TEXT,
                    fetched_at TEXT NOT NULL,
                    is_trending INTEGER NOT NULL DEFAULT 0,
                    raw_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_articles_published
                    ON articles(published_at DESC);
                CREATE INDEX IF NOT EXISTS idx_articles_category
                    ON articles(category);
                CREATE INDEX IF NOT EXISTS idx_articles_trending
                    ON articles(is_trending, published_at DESC);
                CREATE TABLE IF NOT EXISTS refresh_cache (
                    cache_key TEXT PRIMARY KEY,
                    refreshed_at TEXT NOT NULL,
                    fetched_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    email_verified INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_user_sessions_expires
                    ON user_sessions(expires_at);
                CREATE TABLE IF NOT EXISTS auth_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_purpose
                    ON auth_tokens(user_id, purpose, expires_at);
                CREATE TABLE IF NOT EXISTS oauth_accounts (
                    provider TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(provider, subject),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state_hash TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_rate_limits (
                    bucket TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    window_started INTEGER NOT NULL,
                    attempt_count INTEGER NOT NULL,
                    blocked_until INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(bucket, key_hash)
                );
                """
            )
            user_columns = {
                str(row["name"]) for row in conn.execute("PRAGMA table_info(users)").fetchall()
            }
            if "email_verified" not in user_columns:
                conn.execute(
                    "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0"
                )

    def existing_ids(self, article_ids: list[str]) -> set[str]:
        if not article_ids:
            return set()
        found: set[str] = set()
        with self._connect() as conn:
            # Stay below SQLite's default bound-parameter limit.
            for start in range(0, len(article_ids), 500):
                chunk = article_ids[start : start + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"SELECT id FROM articles WHERE id IN ({placeholders})", chunk
                ).fetchall()
                found.update(str(row["id"]) for row in rows)
        return found

    def upsert_many(self, articles: list[dict[str, Any]]) -> int:
        if not articles:
            return 0
        sql = """
            INSERT INTO articles (
                id, headline, description, source, provider, author, url,
                image_url, category, published_at, fetched_at, is_trending, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                headline=excluded.headline,
                description=CASE WHEN length(excluded.description) > length(articles.description)
                                 THEN excluded.description ELSE articles.description END,
                source=excluded.source,
                provider=excluded.provider,
                author=COALESCE(excluded.author, articles.author),
                url=excluded.url,
                image_url=COALESCE(excluded.image_url, articles.image_url),
                category=excluded.category,
                published_at=COALESCE(excluded.published_at, articles.published_at),
                fetched_at=excluded.fetched_at,
                is_trending=MAX(excluded.is_trending, articles.is_trending),
                raw_json=excluded.raw_json
        """
        rows = [
            (
                a["id"], a["headline"], a.get("description", ""), a["source"],
                a["provider"], a.get("author"), a["url"], a.get("image_url"),
                a.get("category", "World"), a.get("published_at"), a["fetched_at"],
                int(bool(a.get("is_trending"))), json.dumps(a.get("raw", {}), ensure_ascii=False),
            )
            for a in articles
        ]
        with self._connect() as conn:
            conn.executemany(sql, rows)
        return len(rows)

    def mark_refresh(self, key: str, fetched_count: int) -> str:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO refresh_cache(cache_key, refreshed_at, fetched_count)
                   VALUES (?, ?, ?)
                   ON CONFLICT(cache_key) DO UPDATE SET
                   refreshed_at=excluded.refreshed_at, fetched_count=excluded.fetched_count""",
                (key, now, fetched_count),
            )
        return now

    def cache_info(self, key: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM refresh_cache WHERE cache_key=?", (key,)
            ).fetchone()

    def cache_is_fresh(self, key: str, ttl_seconds: int) -> bool:
        row = self.cache_info(key)
        if not row:
            return False
        try:
            refreshed = datetime.fromisoformat(row["refreshed_at"])
            return refreshed >= datetime.now(UTC) - timedelta(seconds=ttl_seconds)
        except (TypeError, ValueError):
            return False

    def search(
        self,
        query: str | None = None,
        category: str | None = None,
        sort: str = "newest",
        limit: int = 40,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where, params = [], []
        if query:
            terms = [term for term in query.strip().split() if term][:8]
            if terms:
                term_clauses = []
                for term in terms:
                    term_clauses.append(
                        "(headline LIKE ? OR description LIKE ? OR source LIKE ?)"
                    )
                    token = f"%{term}%"
                    params.extend([token, token, token])
                where.append("(" + " OR ".join(term_clauses) + ")")
        if category and category.lower() != "all":
            where.append("category = ?")
            params.append(category)
        order = {
            "newest": "COALESCE(published_at, fetched_at) DESC",
            "trending": "is_trending DESC, COALESCE(published_at, fetched_at) DESC",
            "relevant": "is_trending DESC, COALESCE(published_at, fetched_at) DESC",
        }.get(sort, "COALESCE(published_at, fetched_at) DESC")
        sql = "SELECT * FROM articles"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {order} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def get(self, article_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM articles WHERE id=?", (article_id,)
            ).fetchone()
            return dict(row) if row else None

    def create_user(
        self,
        user_id: str,
        name: str,
        email: str,
        password_hash: str,
        created_at: str,
        email_verified: bool = False,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO users(id,name,email,password_hash,email_verified,created_at)
                   VALUES(?,?,?,?,?,?)""",
                (user_id, name, email, password_hash, int(email_verified), created_at),
            )
        return {
            "id": user_id,
            "name": name,
            "email": email,
            "email_verified": bool(email_verified),
            "created_at": created_at,
        }

    def user_by_email(self, email: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,)
            ).fetchone()
            return dict(row) if row else None

    def create_session(
        self, token_hash: str, user_id: str, created_at: str, expires_at: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO user_sessions(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)",
                (token_hash, user_id, created_at, expires_at),
            )
            conn.execute("DELETE FROM user_sessions WHERE expires_at <= ?", (created_at,))

    def user_by_session(self, token_hash: str, now: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT users.id, users.name, users.email, users.email_verified, users.created_at
                   FROM user_sessions JOIN users ON users.id=user_sessions.user_id
                   WHERE user_sessions.token_hash=? AND user_sessions.expires_at>?""",
                (token_hash, now),
            ).fetchone()
            return dict(row) if row else None

    def delete_session(self, token_hash: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM user_sessions WHERE token_hash=?", (token_hash,))

    def create_auth_token(
        self,
        token_hash: str,
        user_id: str,
        purpose: str,
        created_at: str,
        expires_at: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM auth_tokens WHERE expires_at<=?", (created_at,))
            conn.execute(
                "DELETE FROM auth_tokens WHERE user_id=? AND purpose=? AND used_at IS NULL",
                (user_id, purpose),
            )
            conn.execute(
                """INSERT INTO auth_tokens(token_hash,user_id,purpose,created_at,expires_at)
                   VALUES(?,?,?,?,?)""",
                (token_hash, user_id, purpose, created_at, expires_at),
            )

    def consume_auth_token(
        self, token_hash: str, purpose: str, now: str
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT auth_tokens.user_id, users.id, users.name, users.email,
                          users.email_verified, users.created_at
                   FROM auth_tokens JOIN users ON users.id=auth_tokens.user_id
                   WHERE auth_tokens.token_hash=? AND auth_tokens.purpose=?
                     AND auth_tokens.used_at IS NULL AND auth_tokens.expires_at>?""",
                (token_hash, purpose, now),
            ).fetchone()
            if not row:
                return None
            updated = conn.execute(
                "UPDATE auth_tokens SET used_at=? WHERE token_hash=? AND used_at IS NULL",
                (now, token_hash),
            )
            if updated.rowcount != 1:
                return None
            return dict(row)

    def mark_email_verified(self, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE users SET email_verified=1 WHERE id=?", (user_id,))

    def update_password(self, user_id: str, password_hash: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id)
            )
            conn.execute("DELETE FROM user_sessions WHERE user_id=?", (user_id,))
            conn.execute(
                "UPDATE auth_tokens SET used_at=COALESCE(used_at, ?) WHERE user_id=? AND purpose='password_reset'",
                (datetime.now(UTC).isoformat(), user_id),
            )

    def create_oauth_state(self, state_hash: str, provider: str, expires_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM oauth_states WHERE expires_at<=?",
                (datetime.now(UTC).isoformat(),),
            )
            conn.execute(
                "INSERT INTO oauth_states(state_hash,provider,expires_at) VALUES(?,?,?)",
                (state_hash, provider, expires_at),
            )

    def consume_oauth_state(self, state_hash: str, provider: str, now: str) -> bool:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT 1 FROM oauth_states WHERE state_hash=? AND provider=? AND expires_at>?",
                (state_hash, provider, now),
            ).fetchone()
            conn.execute("DELETE FROM oauth_states WHERE state_hash=?", (state_hash,))
            conn.execute("DELETE FROM oauth_states WHERE expires_at<=?", (now,))
            return bool(row)

    def user_by_oauth(self, provider: str, subject: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT users.* FROM oauth_accounts
                   JOIN users ON users.id=oauth_accounts.user_id
                   WHERE oauth_accounts.provider=? AND oauth_accounts.subject=?""",
                (provider, subject),
            ).fetchone()
            return dict(row) if row else None

    def link_oauth_account(
        self, provider: str, subject: str, user_id: str, created_at: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO oauth_accounts(provider,subject,user_id,created_at)
                   VALUES(?,?,?,?)""",
                (provider, subject, user_id, created_at),
            )

    def consume_rate_limit(
        self,
        bucket: str,
        key_hash: str,
        now_epoch: int,
        limit: int,
        window_seconds: int,
        block_seconds: int,
    ) -> tuple[bool, int]:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM auth_rate_limits WHERE blocked_until<=? AND window_started<?",
                (now_epoch, now_epoch - 604_800),
            )
            row = conn.execute(
                "SELECT * FROM auth_rate_limits WHERE bucket=? AND key_hash=?",
                (bucket, key_hash),
            ).fetchone()
            if row and int(row["blocked_until"]) > now_epoch:
                return False, int(row["blocked_until"]) - now_epoch
            if not row or now_epoch - int(row["window_started"]) >= window_seconds:
                conn.execute(
                    """INSERT INTO auth_rate_limits(bucket,key_hash,window_started,attempt_count,blocked_until)
                       VALUES(?,?,?,?,0)
                       ON CONFLICT(bucket,key_hash) DO UPDATE SET
                         window_started=excluded.window_started,
                         attempt_count=excluded.attempt_count,
                         blocked_until=0""",
                    (bucket, key_hash, now_epoch, 1),
                )
                return True, 0
            attempts = int(row["attempt_count"]) + 1
            if attempts > limit:
                blocked_until = now_epoch + block_seconds
                conn.execute(
                    "UPDATE auth_rate_limits SET attempt_count=?,blocked_until=? WHERE bucket=? AND key_hash=?",
                    (attempts, blocked_until, bucket, key_hash),
                )
                return False, block_seconds
            conn.execute(
                "UPDATE auth_rate_limits SET attempt_count=? WHERE bucket=? AND key_hash=?",
                (attempts, bucket, key_hash),
            )
            return True, 0

    def clear_rate_limit(self, bucket: str, key_hash: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM auth_rate_limits WHERE bucket=? AND key_hash=?",
                (bucket, key_hash),
            )

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0])

    def prune(self, days: int = 30) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM articles WHERE fetched_at < ?", (cutoff,)
            )
            return cur.rowcount
