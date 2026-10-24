#!/usr/bin/env bash
# Post-deploy wiring: Gmail push subscription, Telegram webhook, migrate job run, health check.
# Usage: bash infra/80_webhooks.sh   (after 60_deploy.sh; needs TELEGRAM_BOT_TOKEN secret value set)
set -euo pipefail
source "$(dirname "$0")/vars.sh"
API_URL=$(gcloud run services describe cm-api --region="$REGION" --format='value(status.url)')

gcloud pubsub subscriptions create gmail-push-sub --topic=gmail-push \
  --push-endpoint="$API_URL/webhooks/gmail" --push-auth-service-account="$SA_PUSH" \
  --push-auth-token-audience="$API_URL/webhooks/gmail" \
  --dead-letter-topic=dead-letter --max-delivery-attempts=10 --ack-deadline=20 \
  --min-retry-delay=10s --max-retry-delay=600s || true
gcloud pubsub subscriptions add-iam-policy-binding gmail-push-sub \
  --member="serviceAccount:$PUBSUB_AGENT" --role=roles/pubsub.subscriber >/dev/null

# Telegram: secrets are read here and sent only to api.telegram.org and never printed.
bash "$(dirname "$0")/../scripts/set_telegram_webhook.sh" "$API_URL" --from-secret-manager

gcloud run jobs execute cm-migrate --region="$REGION" --wait
curl -fsS "$API_URL/healthz" && echo
# Gmail watch: call the worker renew task once (OIDC) or locally `python -m cm.channels.gmail --watch`
echo "80_webhooks: done."
