# TRUTHSCAN API Key Setup

This is the single folder for configuring Gemini, X, Meta content access, YouTube, Google Fact Check, optional news providers, SMTP email, and Google/Meta social login.

## Destination

Use the `API_KEY_SETUP` folder inside your local TRUTHSCAN repository.

## Steps

1. Create the ignored local credential file from the safe template.

   PowerShell:

   ```powershell
   Copy-Item API_KEY_SETUP\1_PUT_KEYS_HERE.env.example API_KEY_SETUP\1_PUT_KEYS_HERE.env
   ```

   Git Bash/Linux/macOS:

   ```bash
   cp API_KEY_SETUP/1_PUT_KEYS_HERE.env.example API_KEY_SETUP/1_PUT_KEYS_HERE.env
   ```

2. Open **`1_PUT_KEYS_HERE.env`**.
3. Enter only the credentials you want to enable. Leave unused entries blank.
4. Save it. Never paste the completed file into chat or GitHub.
5. In Git Bash/Linux/macOS, install the entered values with:

   ```bash
   cd API_KEY_SETUP
   ./2_INSTALL_KEYS.sh
   ```

   On Windows PowerShell, you can instead copy the required nonblank settings into `backend\.env` manually; both completed files are ignored by Git.

6. Restart the backend. Configuration is loaded only when the API starts.
7. Check `GET /api/v1/health`. Enabled provider names appear there, but credential values are never returned.

The installer securely merges nonblank setup fields into the backend's protected destination:

```text
backend/.env
```

Blank setup fields do not erase credentials already installed there. Both files are restricted to owner-only permissions (`600`) and are excluded from Git; credential values are never printed.

## Provider fields

- `GEMINI_API_KEY`: YouTube spoken-audio and sampled-frame claim extraction.
- `YOUTUBE_API_KEY`: richer YouTube title, description, channel, and publication metadata.
- `GOOGLE_FACT_CHECK_API_KEY`: structured Google Fact Check ClaimReview searches.
- `X_BEARER_TOKEN`: official X API v2 Post lookup.
- `META_ACCESS_TOKEN`: approved Meta Graph API token.
- `META_INSTAGRAM_ACCOUNT_ID`: numeric ID of the authorized Instagram professional account.
- `GNEWS_API_KEY` / `NEWSAPI_KEY`: optional additional news coverage.
- `TRUTHSCAN_APP_BASE_URL`: public HTTPS origin used in email and OAuth callbacks (for example, `https://truthscan.example`).
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_USE_TLS`: transactional email delivery for verification and password recovery.
- `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`: Google OAuth web-application credentials.
- `META_OAUTH_APP_ID` / `META_OAUTH_APP_SECRET`: Meta Login app credentials; these are separate from the Meta Graph content token.

Register the exact provider callbacks below, replacing the example origin with `TRUTHSCAN_APP_BASE_URL`:

```text
https://truthscan.example/api/v1/auth/oauth/google/callback
https://truthscan.example/api/v1/auth/oauth/meta/callback
```

Google and Meta buttons remain visibly disabled until both fields for that provider are installed and the backend is restarted. If SMTP is absent in development, TRUTHSCAN returns a one-time action link for local testing; production never exposes verification or reset links in API responses.

## Where to obtain Meta, Instagram, and X credentials

### Meta and Instagram

1. Register at `https://developers.facebook.com/` and open `https://developers.facebook.com/apps/`.
2. Create a Meta app and add the Facebook Login and/or Instagram use case required for your account type.
3. Copy the App ID and App Secret for `META_OAUTH_APP_ID` and `META_OAUTH_APP_SECRET` when configuring Meta social login.
4. Generate an approved User/Page access token for Graph API content access and store it as `META_ACCESS_TOKEN`.
5. For the current TRUTHSCAN Instagram resolver, use a Business or Creator account authorized by that token and set its numeric professional account ID as `META_INSTAGRAM_ACCOUNT_ID`.

The App Secret is not the same as an access token. The current resolver can inspect media exposed for the configured authorized professional account; it cannot use a generic “Instagram API key” to read arbitrary personal or public profiles.

Official starting points:

- `https://developers.facebook.com/docs/development/create-an-app/`
- `https://developers.facebook.com/docs/instagram-platform/overview/`
- `https://developers.facebook.com/docs/instagram-platform/create-an-instagram-app/`
- `https://developers.facebook.com/docs/facebook-login/guides/access-tokens/`

### X

1. Register at `https://console.x.com/` and create a developer app.
2. Open the app's **Keys and Tokens** section.
3. Generate an app-only Bearer Token with an access plan that permits the required X API v2 Post lookup.
4. Store it as `X_BEARER_TOKEN`.

Official starting points:

- `https://docs.x.com/x-api/introduction`
- `https://docs.x.com/fundamentals/authentication/oauth-2-0/overview`

Never paste App Secrets, access tokens, or bearer tokens into frontend JavaScript, GitHub, screenshots, or chat.

## Production security

The local setup file is permission-restricted, but it is not an encrypted secret manager. For production, store values in your hosting provider's encrypted secrets system and use the supported mounted-file variables:

```env
GEMINI_API_KEY_FILE=/run/secrets/truthscan_gemini_key
X_BEARER_TOKEN_FILE=/run/secrets/truthscan_x_bearer_token
META_ACCESS_TOKEN_FILE=/run/secrets/truthscan_meta_access_token
SMTP_PASSWORD_FILE=/run/secrets/truthscan_smtp_password
GOOGLE_OAUTH_CLIENT_SECRET_FILE=/run/secrets/truthscan_google_oauth_secret
META_OAUTH_APP_SECRET_FILE=/run/secrets/truthscan_meta_oauth_secret
```

Never put credentials in `app.js`, HTML, browser storage, screenshots, commits, or normal chat messages.
