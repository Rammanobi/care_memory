#!/usr/bin/env bash
# Post-deploy wiring: migrate job, Telegram webhook (via 90), health check; Gmail push only if ENABLE_GMAIL_PUSH=1.
# Usage: bash infra/80_webhooks.sh   (after 60_deploy.sh; needs TELEGRAM_BOT_TOKEN secret value set)
set -euo pipefail
source "$(dirname "$0")/vars.sh"
API_URL=$(gcloud run services describe cm-api --region="$REGION" --format='value(status.url)')

# Gmail push subscription: skipped until /webhooks/gmail exists (otherwise Pub/Sub retries into the DLQ).
# Enable with ENABLE_GMAIL_PUSH=1 once the route is deployed.
if [ "${ENABLE_GMAIL_PUSH:-0}" = "1" ]; then
  gcloud pubsub subscriptions create gmail-push-sub --topic=gmail-push \
    --push-endpoint="$API_URL/webhooks/gmail" --push-auth-service-account="$SA_PUSH" \
    --push-auth-token-audience="$API_URL/webhooks/gmail" \
    --dead-letter-topic=dead-letter --max-delivery-attempts=10 --ack-deadline=20 \
    --min-retry-delay=10s --max-retry-delay=600s || true
  gcloud pubsub subscriptions add-iam-policy-binding gmail-push-sub \
    --member="serviceAccount:$PUBSUB_AGENT" --role=roles/pubsub.subscriber >/dev/null
fi

# Migrate first (the webhook handler needs the schema), then Telegram on the run.app URL.
# Once the LB cert is ACTIVE, switch to the domain with infra/90_telegram_webhook.sh.
gcloud sql backups create --instance=cm-pg || echo "WARN: backup failed (continuing)"
gcloud run jobs execute cm-migrate --region="$REGION" --wait
bash "$(dirname "$0")/90_telegram_webhook.sh" "$API_URL"
curl -fsS "$API_URL/healthz" && echo
# Gmail watch: call the worker renew task once (OIDC) or locally `python -m cm.channels.gmail --watch`
echo "80_webhooks: done."
