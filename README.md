# TRUTHSCAN

India-first live news, current-rumour discovery, attributed fact-checking, and evidence-based verification built with FastAPI, SQLite, and a responsive editorial frontend.

## Current capabilities

- Live hybrid news retrieval from publisher RSS and Google News discovery.
- Latest-rumour desk restricted to a rolling 14-day publication window.
- Feed-level labels: **Debunked by Fact-Checkers**, **Supported by Verified News Source**, or **More Verification Needed**.
- In-app evidence reports with closest reporting, named publishers, fact-check ratings, corrections, and limitations.
- Text, URL, public social-link, and screenshot verification.
- Secure accounts with PBKDF2 password hashes, HttpOnly sessions, email verification, password reset, OAuth scaffolding, and persistent rate limits.
- Optional Gemini, X, Meta, YouTube, Google Fact Check, GNews, and NewsAPI integrations.

No confidence percentage is presented as a probability of truth. Missing coverage is not treated as proof that a claim is fake.

## Repository layout

```text
truthscan/
├── index.html                 # Single-page frontend shell
├── app.js                     # Frontend application and API integration
├── styles.css                 # Editorial responsive design
├── data.js                    # Clearly labelled offline/demo fallback items
├── backend/
│   ├── app/                   # FastAPI application and services
│   ├── requirements.txt       # Python dependencies
│   ├── .env.example           # Safe backend configuration template
│   └── README.md              # Detailed API and architecture documentation
├── API_KEY_SETUP/
│   ├── 1_PUT_KEYS_HERE.env.example
│   ├── 2_INSTALL_KEYS.sh
│   └── README.md
└── docs/
    └── GITHUB_WINDOWS.md      # Windows 11 GitHub instructions
```

Runtime secrets, the SQLite database, caches, and virtual environments are deliberately excluded from Git.

## Run locally on Windows 11

Open PowerShell in the repository folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

If PowerShell blocks activation, either use Command Prompt with `.venv\Scripts\activate.bat`, or run the virtual-environment executables directly.

## Credentials

Do not commit real credentials. For local setup:

```powershell
Copy-Item API_KEY_SETUP\1_PUT_KEYS_HERE.env.example API_KEY_SETUP\1_PUT_KEYS_HERE.env
```

Fill the copied file locally. See [`API_KEY_SETUP/README.md`](API_KEY_SETUP/README.md). Production credentials belong in the hosting provider's encrypted environment/secrets settings.

## Documentation

- [Windows 11 GitHub workflow](docs/GITHUB_WINDOWS.md)
- [Backend API and architecture](backend/README.md)
- [Credential setup](API_KEY_SETUP/README.md)

## Deployment note

GitHub stores the source code but GitHub Pages cannot run this complete application because it needs FastAPI, SQLite/PostgreSQL, background verification, SMTP, and backend-only provider credentials. Connect the GitHub repository to a Python host such as Render, Railway, Fly.io, or a cloud VM/container service.
