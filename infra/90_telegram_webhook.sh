#!/usr/bin/env bash
# Switch the Telegram bot from long polling (laptop tg_poll) to a webhook on the cloud URL.
# Usage: bash infra/90_telegram_webhook.sh [base-url]
#   no argument -> https://$DOMAIN (needs DOMAIN; use once the LB cert is ACTIVE)
#   run.app URL -> use before the cert is ready: bash infra/90_telegram_webhook.sh https://cm-api-xxxx.a.run.app
# DRY_RUN=1 prints the target only. The bot token and webhook secret are read from Secret Manager at run
# time into shell variables and sent only to api.telegram.org; they are never printed or put in argv.
# STOP the laptop poller first (python -m cm.jobs.tg_poll): it calls deleteWebhook and would undo this.
set -euo pipefail
source "$(dirname "$0")/vars.sh"
if [ -n "${1:-}" ]; then BASE="${1%/}"; else need_domain; BASE="https://$DOMAIN"; fi
case "$BASE" in https://*) ;; *) echo "base URL must be https" >&2; exit 1 ;; esac
TARGET="$BASE/webhooks/telegram"
echo "webhook target: $TARGET"
if [ "$DRY_RUN" = "1" ]; then echo "[dry-run] would call setWebhook (token from Secret Manager, not printed)"; exit 0; fi

TOKEN=$(gcloud secrets versions access latest --secret=TELEGRAM_BOT_TOKEN)
SECRET=$(gcloud secrets versions access latest --secret=TELEGRAM_WEBHOOK_SECRET)
[ -n "$TOKEN" ] && [ -n "$SECRET" ] || { echo "TELEGRAM_BOT_TOKEN / TELEGRAM_WEBHOOK_SECRET have no value" >&2; exit 1; }
# curl --config - keeps the token out of the process list (argv) and out of any trace output.
printf 'url = "https://api.telegram.org/bot%s/setWebhook"\n' "$TOKEN" | curl -fsS --config - \
  --data-urlencode "url=$TARGET" --data-urlencode "secret_token=$SECRET" \
  --data-urlencode 'allowed_updates=["message","callback_query"]' -d drop_pending_updates=true >/dev/null
echo "setWebhook sent"
printf 'url = "https://api.telegram.org/bot%s/getWebhookInfo"\n' "$TOKEN" | curl -fsS --config - | \
  python -c 'import json,sys; d=json.load(sys.stdin).get("result",{}); print("registered url:", d.get("url")); print("pending:", d.get("pending_update_count"), "last_error:", d.get("last_error_message"))'
unset TOKEN SECRET
