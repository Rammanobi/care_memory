#!/usr/bin/env bash
# STUB: register the Telegram webhook for a base URL.
# Usage:
#   bash scripts/set_telegram_webhook.sh https://xxxx.ngrok-free.app            # token/secret from .env
#   bash scripts/set_telegram_webhook.sh https://cm-api-xxx.run.app --from-secret-manager
#   bash scripts/set_telegram_webhook.sh --dry-run https://example.test          # prints the target, sends nothing
# Uses TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET; values are never printed. One bot = one webhook,
# so use a separate dev bot locally.
set -euo pipefail
DRY=0; if [ "${1:-}" = "--dry-run" ]; then DRY=1; shift; fi
BASE="${1:?usage: set_telegram_webhook.sh <base-url> [--from-secret-manager]}"
if [ "${2:-}" = "--from-secret-manager" ]; then
  TELEGRAM_BOT_TOKEN=$(gcloud secrets versions access latest --secret=TELEGRAM_BOT_TOKEN)
  TELEGRAM_WEBHOOK_SECRET=$(gcloud secrets versions access latest --secret=TELEGRAM_WEBHOOK_SECRET)
elif [ -f .env ]; then
  set -a; source .env; set +a
fi
echo "webhook target: ${BASE%/}/webhooks/telegram"
[ "$DRY" = 1 ] && exit 0
: "${TELEGRAM_BOT_TOKEN:?missing}"; : "${TELEGRAM_WEBHOOK_SECRET:?missing}"
curl -fsS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${BASE%/}/webhooks/telegram" -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
  -d drop_pending_updates=true --data-urlencode 'allowed_updates=["message","callback_query"]'
echo
