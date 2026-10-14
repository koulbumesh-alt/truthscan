# TRUTHSCAN AI Backend

Python/FastAPI backend that aggregates live news and performs transparent, cross-source evidence verification.

## What is implemented

- India-first hybrid ingestion from Google News discovery and direct publisher RSS feeds.
- Direct Indian feeds include Aaj Tak, NDTV, India Today, ABP Live/ABP Hindi, Times of India, The Hindu, Hindustan Times, India TV, TV9 Bharatvarsh, Greater Kashmir, The Wire, and Scroll.in.
- Publisher-specific discovery includes Zee News, News18, Indian Express, Times Now, ThePrint, Republic World, DD News, WION, and Daily Excelsior where direct feeds are blocked or unavailable.
- International/subject feeds include BBC sections, Al Jazeera, NASA, and TechCrunch.
- Optional GNews and NewsAPI adapters, enabled only when their server-side API keys exist.
- Normalized article schema, headline deduplication, SQLite cache, 5-minute refresh TTL, source isolation, and graceful partial failure.
- Every live news and rumour feed item carries one transparent feed-level status: `DEBUNKED BY FACT-CHECKERS`, `SUPPORTED BY VERIFIED NEWS SOURCE`, or `MORE VERIFICATION NEEDED`. Debunked requires explicit negative wording from an attributed fact-check review; supported is provisional under the reviewed-publisher policy; every item links to a complete in-app evidence check that can supersede the lightweight feed status.
- Federated query search with deterministic relevance ranking, closest headline matches, and related coverage from other publishers. Every submitted search also runs an attributed rumour/fact-check scan limited to reviews published within the latest 14 days, places the closest current reviews first, links their ratings and correcting evidence, and only shows a debunked outcome when a sufficiently close negative review is identified.
- On-demand provenance verification of submitted headlines, claims, URLs, live articles, and supported public social links—without confidence percentages.
- Live social-link resolution for YouTube/Shorts, TikTok, X, and Reddit; optional YouTube Data API metadata via `YOUTUBE_API_KEY`.
- Actual YouTube audio and sampled-frame claim extraction through Google's official video-understanding API when `GEMINI_API_KEY` is configured. Fast videos use direct processing; requests that exceed the direct timeout automatically switch to Gemini background execution and are polled as verification jobs. Extracted claims are searched against live publishers and fact-checkers; model output itself is never treated as proof.
- Official X API v2 Post lookup when `X_BEARER_TOKEN` is configured, with transparent public-oEmbed fallback when the API is unavailable.
- Official Meta Graph API support for permitted Facebook Page posts/videos and media belonging to the configured authorized Instagram professional account. Meta links are never analyzed from a generic login page or by repurposing oEmbed output.
- One strongly matching report from a publisher in TRUTHSCAN's reviewed source registry is sufficient for `SUPPORTED BY A VERIFIED NEWS SOURCE`, provided no attributable debunk is found. The support is explicitly provisional and can be superseded by a later correction. Multiple-source support remains a separate outcome; unrecognized or weak matches remain “reported by named sources — needs more verification.”
- Dedicated live rumours/fact-check stream from Alt News, BOOM, FACTLY, Newschecker, Vishvas News, Fact Crescendo, and English/Hindi Google News discovery, with on-demand refresh. The visible stream is newest-first and uses a strict rolling 14-day publication window; older reviews and items without a reliable publication date are excluded. Refresh responses distinguish genuinely new records from existing records that were refreshed.
- Functional account signup/sign-in backed by SQLite, salted PBKDF2-SHA256 password hashes, revocable 30-day HttpOnly sessions, one-time email verification, and one-time password recovery. SMTP delivery is supported; explicit `development` mode returns test action links, while every other environment suppresses them.
- Google and Meta authorization-code social login with server-side token exchange, hashed single-use state records, an initiating-browser HttpOnly state cookie, and automatic verified-email account linking. Providers remain disabled until real credentials are configured.
- Persistent SQLite authentication limits for signup, login, verification resend, forgotten-password, reset, and OAuth starts. Limits survive process restarts and return `429` with `Retry-After`.
- Optional Google Fact Check Tools integration for structured ClaimReview ratings, with recognized Indian fact-checker article discovery as a no-key fallback.
- Screenshot verification with temporary local OCR (English and optional Hindi), followed by the same reporting and fact-check searches. Uploaded images are not retained.
- Same-origin frontend hosting so secrets are never sent to browser JavaScript.
- Interactive OpenAPI documentation at `/api/docs`.

## Requirements

- Python 3.11 or newer (3.13 is used in this workspace)
- Internet access for live feeds
- `pip` and the packages in `requirements.txt`
- Tesseract OCR for screenshot text extraction (`tesseract-ocr`, English data, and optionally Hindi data)
- Recommended `GOOGLE_FACT_CHECK_API_KEY` for structured publisher ratings
- Recommended `YOUTUBE_API_KEY` for richer public video metadata
- Recommended `GEMINI_API_KEY` for actual public YouTube audio/frame claim extraction (`GEMINI_MODEL` defaults to `gemini-3.8-flash`)
- Optional `X_BEARER_TOKEN` with X API access for official Post lookup
- Optional `META_ACCESS_TOKEN`, approved Meta permissions, and `META_INSTAGRAM_ACCOUNT_ID` for permitted Meta content
- Optional `GNEWS_API_KEY` and/or `NEWSAPI_KEY` for additional news coverage
- SMTP account for production email verification/password recovery
- Google OAuth web client and/or Meta Login app for optional social login, with exact registered callbacks

## Local setup

```bash
cd truthscan
# Ubuntu/Debian screenshot OCR (Hindi package is optional)
sudo apt-get install tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin

python -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env  # optional
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000`. API documentation is at `http://localhost:8000/api/docs`.

## API routes

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Service, database, and provider status |
| GET | `/api/v1/auth/providers` | Report whether SMTP and each social provider are configured (never credentials) |
| POST | `/api/v1/auth/signup` | Create an unverified account, start an HttpOnly session, and prepare verification |
| POST | `/api/v1/auth/login` | Sign in and start a session |
| GET | `/api/v1/auth/me` | Return the signed-in public profile and email-verification status |
| POST | `/api/v1/auth/verify-email` | Consume a single-use verification token |
| POST | `/api/v1/auth/resend-verification` | Prepare a fresh verification email/link with an enumeration-safe response |
| POST | `/api/v1/auth/forgot-password` | Prepare a single-use, 30-minute reset email/link with an enumeration-safe response |
| POST | `/api/v1/auth/reset-password` | Consume a reset token, change the password, and revoke existing sessions |
| GET | `/api/v1/auth/oauth/{provider}/start` | Start Google or Meta authorization-code login when configured |
| GET | `/api/v1/auth/oauth/{provider}/callback` | Validate browser-bound state, exchange the code, and start a session |
| POST | `/api/v1/auth/logout` | Revoke the current session |
| GET | `/api/v1/sources` | Configured and enabled feed/API sources |
| GET | `/api/v1/news` | Live news with `q`, `category`, `sort`, `limit`, `offset` |
| GET | `/api/v1/news/trending` | Trending-first live results |
| GET | `/api/v1/news/{id}` | One cached live article |
| GET | `/api/v1/rumours` | Recent reviews of viral claims from connected fact-check feeds |
| POST | `/api/v1/rumours/refresh` | Force-refresh the rumours and fact-check stream |
| POST | `/api/v1/verify/text` | Synchronously verify submitted text or a public URL |
| POST | `/api/v1/verify/jobs` | Start a background-capable text/link verification job |
| GET | `/api/v1/verify/jobs/{job_id}` | Poll a verification job without keeping one long browser request open |
| POST | `/api/v1/verify/article/{id}` | Verify a cached live article against other coverage |
| POST | `/api/v1/verify/image` | OCR a screenshot and verify the extracted claim |
| POST | `/api/v1/news/refresh` | Force refresh; optional `X-Admin-Key` protection |

Example:

```bash
curl 'http://localhost:8000/api/v1/news?q=artificial%20intelligence&category=Technology&limit=10'
```

## SQLite now, PostgreSQL later

SQLite is used for the first version because it needs no separate database server. All SQL access is isolated in `app/database.py`. For production, implement the same repository methods with PostgreSQL/SQLAlchemy, add migrations (Alembic), and point the service at that repository.

The SQLite file is generated at `backend/data/truthscan.db` and should not be committed.

## Secure provider access

Provider credentials are backend-only and are sent to their official HTTPS endpoints in request headers. They are never returned by an API, embedded in browser JavaScript, included in request URLs, or intentionally logged.

For production, keep credentials in an encrypted cloud/deployment secret manager and mount the decrypted values only inside the API container:

```env
GEMINI_API_KEY_FILE=/run/secrets/truthscan_gemini_key
X_BEARER_TOKEN_FILE=/run/secrets/truthscan_x_bearer_token
META_ACCESS_TOKEN_FILE=/run/secrets/truthscan_meta_access_token
SMTP_PASSWORD_FILE=/run/secrets/truthscan_smtp_password
GOOGLE_OAUTH_CLIENT_SECRET_FILE=/run/secrets/truthscan_google_oauth_secret
META_OAUTH_APP_SECRET_FILE=/run/secrets/truthscan_meta_oauth_secret
GEMINI_MODEL=gemini-3.8-flash
META_GRAPH_VERSION=v26.0
META_INSTAGRAM_ACCOUNT_ID=your_authorized_professional_account_id
```

Each `*_FILE` option takes precedence over its direct environment-variable equivalent. Docker Secrets, Kubernetes-mounted secrets backed by encryption at rest, Google Secret Manager, AWS Secrets Manager, and equivalent services can supply these files. Do not place real credentials in the repository or container image.

For local-only development, `GEMINI_API_KEY`, `X_BEARER_TOKEN`, and `META_ACCESS_TOKEN` in `backend/.env` are supported. The file is Git-ignored and permission-restricted (`chmod 600 backend/.env`). Environment or mounted-secret changes require an API restart.

### Email and social-login configuration

Set `TRUTHSCAN_APP_BASE_URL` to the public HTTPS origin. Configure SMTP with `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` (or `SMTP_PASSWORD_FILE`), `SMTP_FROM_EMAIL`, and `SMTP_USE_TLS`. Production intentionally omits development action URLs, so SMTP must work before public deployment.

Register these exact callback paths in the provider consoles:

```text
{TRUTHSCAN_APP_BASE_URL}/api/v1/auth/oauth/google/callback
{TRUTHSCAN_APP_BASE_URL}/api/v1/auth/oauth/meta/callback
```

Then configure `GOOGLE_OAUTH_CLIENT_ID` plus its secret, and/or `META_OAUTH_APP_ID` plus its secret. OAuth access tokens are used only for the immediate profile request and are not persisted. Social identities are linked by provider subject ID; an existing normalized email is linked only after the provider returns that identity through its verified login flow.

### Provider approval requirements

- **X:** create an X developer project/app with a plan that permits `GET /2/tweets/{id}`, then inject its bearer token.
- **Facebook:** complete Meta business verification and App Review for Page Public Content Access, or use appropriate Page permissions for Pages managed by the app user. The submitted URL must expose a numeric post/video/Reel ID.
- **Instagram:** configure an authorized professional-account ID and approved Instagram permissions. The current resolver matches submitted permalinks against media exposed for that authorized account. It does not scrape or claim arbitrary personal-account access.
- **Broader Meta research access:** Meta Content Library API is a separate controlled-access research product and cannot be used as an unrestricted production-web-app credential.

## Security and content rules

- Keep provider keys in backend environment variables or encrypted deployment secrets; never put them in `app.js`, API responses, source control, or client storage.
- Display headlines, summaries, attribution, and links unless a provider/publisher license explicitly permits full-text republication.
- Google News RSS is useful but undocumented; treat it as a discovery/fallback source, not the only production dependency.
- Honor publisher terms, feed terms, rate limits, robots rules, and image hotlinking restrictions.
- Account passwords are salted and hashed; session, verification, reset, and OAuth-state tokens are stored only as SHA-256 hashes. Sessions and browser-bound OAuth state use HttpOnly SameSite cookies. Set `TRUTHSCAN_ENV=production` so cookies also require HTTPS and development action links are suppressed.
- Authentication rate-limit identifiers are one-way hashed and their SQLite windows persist across process restarts. A reverse proxy/WAF and trusted-proxy configuration should supplement these application limits at larger scale.
- Add security event audit logging, monitored SMTP delivery, abuse alerting, and a production PostgreSQL deployment before a high-traffic public launch.
