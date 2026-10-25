#!/usr/bin/env bash
# Copy DEMO_USER_PASSWORDS from the local .env into Secret Manager WITHOUT printing it.
# The value goes python -> pipe -> `gcloud secrets versions add --data-file=-` (stdin): never on screen, in argv,
# in shell history or in a temp file. Only the cm-seed job (and the optional local-auth fallback) needs it.
# Usage (OWNER, from caremem/, after 30_secrets.sh):  bash infra/35_demo_passwords.sh
#   ENV_FILE=path/to/.env overrides the source file. DRY_RUN=1 validates the JSON and prints the gcloud call only.
set -euo pipefail
source "$(dirname "$0")/vars.sh"
ENV_FILE="${ENV_FILE:-.env}"
[ -f "$ENV_FILE" ] || { echo "35_demo_passwords: $ENV_FILE not found (run from caremem/)" >&2; exit 1; }
PY="$(command -v python || command -v python3)"

# Prints the value (no newline) to stdout ONLY; errors name the variable, never the value.
extract() {
  "$PY" -I -c '
import json, sys
raw = None
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if line.startswith("export "):
        line = line[7:].lstrip()
    if line.startswith("DEMO_USER_PASSWORDS="):
        raw = line.split("=", 1)[1].strip()
if not raw:
    sys.exit("DEMO_USER_PASSWORDS is not set in the env file")
if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\x27\x22":
    raw = raw[1:-1]
try:
    data = json.loads(raw)
except ValueError:
    sys.exit("DEMO_USER_PASSWORDS is not valid JSON (value not shown)")
if not isinstance(data, dict) or not data:
    sys.exit("DEMO_USER_PASSWORDS must be a non-empty JSON object (value not shown)")
sys.stdout.write(raw)
' "$ENV_FILE"
}

if [ "$DRY_RUN" = "1" ]; then
  extract >/dev/null || exit 1
  echo "[dry-run] DEMO_USER_PASSWORDS in $ENV_FILE is valid JSON (value not shown)"
  echo "[dry-run] gcloud secrets versions add DEMO_USER_PASSWORDS --data-file=-" >&2
  exit 0
fi
gcloud secrets describe DEMO_USER_PASSWORDS >/dev/null 2>&1 \
  || { echo "secret DEMO_USER_PASSWORDS does not exist: run infra/30_secrets.sh first" >&2; exit 1; }
extract | gcloud secrets versions add DEMO_USER_PASSWORDS --data-file=- >/dev/null
echo "35_demo_passwords: added a new version of DEMO_USER_PASSWORDS (value not shown)"
