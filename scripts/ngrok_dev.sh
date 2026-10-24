#!/usr/bin/env bash
# STUB: expose the local cm-api over HTTPS with ngrok and register the Telegram webhook.
# Usage: bash scripts/ngrok_dev.sh [--dry-run]   (needs ngrok installed, NGROK_AUTHTOKEN in .env, a DEV bot token)
# --dry-run only prints the public URL of an already-running tunnel.
set -euo pipefail
DRY="${1:-}"
if [ -f .env ]; then set -a; source .env; set +a; fi
if [ -z "$DRY" ] && ! curl -fs http://127.0.0.1:4040/api/tunnels >/dev/null 2>&1; then
  [ -n "${NGROK_AUTHTOKEN:-}" ] && ngrok config add-authtoken "$NGROK_AUTHTOKEN" >/dev/null
  ngrok http 8080 >/dev/null 2>&1 &
  sleep 3
fi
URL=$(curl -fs http://127.0.0.1:4040/api/tunnels | python -c "import sys,json; print(next(t['public_url'] for t in json.load(sys.stdin)['tunnels'] if t['public_url'].startswith('https')))")
echo "public url: $URL  (set PUBLIC_BASE_URL in .env)"
[ "$DRY" = "--dry-run" ] && exit 0
bash "$(dirname "$0")/set_telegram_webhook.sh" "$URL"
