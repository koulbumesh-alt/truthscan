# Push TRUTHSCAN to GitHub from Windows 11

## 1. Download and extract the project

Download the prepared `truthscan-github-ready.zip`, extract it, and open the extracted `truthscan` folder in File Explorer.

Right-click inside the folder and choose **Open in Terminal**, or use PowerShell:

```powershell
cd "$HOME\Documents\truthscan"
```

Adjust the path to the folder you selected.

## 2. Confirm Git identity

```powershell
git --version
git config --global user.name "Your Name"
git config --global user.email "your-github-email@example.com"
```

Use an email associated with your GitHub account, or your GitHub-provided private noreply address.

## 3. Initialize the repository

```powershell
git init
git branch -M main
git add .
git status
```

Before committing, confirm that none of these appear as staged files:

```text
backend/.env
API_KEY_SETUP/1_PUT_KEYS_HERE.env
backend/data/
.venv/
```

Run this safety check:

```powershell
git check-ignore -v backend/.env API_KEY_SETUP/1_PUT_KEYS_HERE.env backend/data/truthscan.db
```

The files should be reported as ignored. Never use `git add -f` on them.

## 4. Commit

```powershell
git commit -m "Initial TRUTHSCAN v1.5.0 release"
```

## 5. Create an empty GitHub repository

1. Sign in at `https://github.com/`.
2. Select **New repository**.
3. Name it `truthscan`.
4. Choose **Private** initially unless you are ready to publish the source.
5. Do not add a README, `.gitignore`, or license during repository creation.
6. Create the repository.

## 6. Add the remote and push

Replace `YOUR_USERNAME`:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/truthscan.git
git remote -v
git push -u origin main
```

GitHub may open a browser authentication window. Git no longer accepts an account password for HTTPS pushes; use the browser credential manager, GitHub CLI authentication, or a personal access token when prompted.

### Optional GitHub CLI workflow

If GitHub CLI is installed:

```powershell
gh auth login
gh repo create truthscan --private --source=. --remote=origin --push
```

Use this instead of manually creating the remote, not in addition to it.

## 7. Normal update workflow

```powershell
git status
git add .
git commit -m "Describe the change"
git push
```

Always inspect `git status` before committing.

## 8. Local credentials after cloning

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item API_KEY_SETUP\1_PUT_KEYS_HERE.env.example API_KEY_SETUP\1_PUT_KEYS_HERE.env
```

Fill only the local copies. They are ignored by Git.

## Full deployment

GitHub is the source repository. To make the complete application public, connect the repository to a Python hosting service and use:

```text
Build: pip install -r backend/requirements.txt
Start: uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
Health check: /api/v1/health
```

Set `TRUTHSCAN_ENV=production`, configure `TRUTHSCAN_APP_BASE_URL`, add SMTP/OAuth/provider credentials through encrypted host settings, and use persistent storage or PostgreSQL for account data.
