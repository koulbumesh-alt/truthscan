#!/usr/bin/env bash
set -euo pipefail

SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SETUP_DIR/.." && pwd)"
SOURCE_FILE="$SETUP_DIR/1_PUT_KEYS_HERE.env"
DESTINATION_FILE="$PROJECT_DIR/backend/.env"
TEMP_FILE="$PROJECT_DIR/backend/.env.installing"

if [[ ! -f "$SOURCE_FILE" ]]; then
  echo "Credential file not found: $SOURCE_FILE" >&2
  exit 1
fi

if ! grep -Eq '^(GEMINI_API_KEY|X_BEARER_TOKEN|META_ACCESS_TOKEN|YOUTUBE_API_KEY|GOOGLE_FACT_CHECK_API_KEY|GNEWS_API_KEY|NEWSAPI_KEY|SMTP_PASSWORD|GOOGLE_OAUTH_CLIENT_SECRET|META_OAUTH_APP_SECRET)=.+' "$SOURCE_FILE"; then
  echo "No API credential has been entered yet." >&2
  echo "Open 1_PUT_KEYS_HERE.env, add at least one key, save it, and run this installer again." >&2
  exit 1
fi

umask 077
SOURCE_FILE="$SOURCE_FILE" DESTINATION_FILE="$DESTINATION_FILE" TEMP_FILE="$TEMP_FILE" python3 - <<'PY'
import os
from pathlib import Path

source = Path(os.environ["SOURCE_FILE"])
destination = Path(os.environ["DESTINATION_FILE"])
temporary = Path(os.environ["TEMP_FILE"])

updates: dict[str, str] = {}
for raw in source.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    if key and value.strip():
        updates[key] = value

existing = destination.read_text(encoding="utf-8").splitlines() if destination.exists() else []
written: set[str] = set()
output: list[str] = []
for raw in existing:
    line = raw.strip()
    if line and not line.startswith("#") and "=" in line:
        key = line.split("=", 1)[0].strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            written.add(key)
            continue
    output.append(raw)

if output and output[-1] != "":
    output.append("")
for key, value in updates.items():
    if key not in written and not any(
        line.strip().startswith(f"{key}=") for line in output
    ):
        output.append(f"{key}={value}")

temporary.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
PY

chmod 600 "$TEMP_FILE"
mv -f "$TEMP_FILE" "$DESTINATION_FILE"
chmod 600 "$SOURCE_FILE" "$DESTINATION_FILE"

echo "Credentials merged securely into: $DESTINATION_FILE"
echo "Blank setup fields did not erase existing credentials, and no value was printed."
echo "Restart the TRUTHSCAN backend to activate changes."
