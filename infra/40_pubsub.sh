#!/usr/bin/env bash
# Pub/Sub topics for Gmail push and the dead-letter flow. The push subscription needs the cm-api URL,
# so it is created in 80_webhooks.sh after the first deploy.
set -euo pipefail
source "$(dirname "$0")/vars.sh"

gcloud pubsub topics create gmail-push || true
gcloud pubsub topics create dead-letter || true
gcloud pubsub topics add-iam-policy-binding gmail-push \
  --member=serviceAccount:gmail-api-push@system.gserviceaccount.com --role=roles/pubsub.publisher >/dev/null
gcloud pubsub subscriptions create dead-letter-sub --topic=dead-letter --ack-deadline=60 || true
gcloud pubsub topics add-iam-policy-binding dead-letter \
  --member="serviceAccount:$PUBSUB_AGENT" --role=roles/pubsub.publisher >/dev/null
echo "40_pubsub: done."
