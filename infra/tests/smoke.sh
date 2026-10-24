#!/usr/bin/env bash
# GCP smoke test: health, worker is private, queues and jobs exist.
# Usage: bash infra/tests/smoke.sh
set -euo pipefail
source "$(dirname "$0")/../vars.sh"
API_URL=$(gcloud run services describe cm-api --region="$REGION" --format='value(status.url)')
WORKER_URL=$(gcloud run services describe cm-worker --region="$REGION" --format='value(status.url)')

curl -fsS "$API_URL/healthz" >/dev/null && echo "ok: cm-api /healthz"
code=$(curl -s -o /dev/null -w '%{http_code}' "$WORKER_URL/healthz")
[ "$code" = "401" ] || [ "$code" = "403" ] && echo "ok: cm-worker rejects anonymous ($code)" || { echo "FAIL: worker returned $code"; exit 1; }
for q in agent-runs resumes outbound; do gcloud tasks queues describe "$q" --location="$REGION" >/dev/null && echo "ok: queue $q"; done
for j in cm-migrate cm-seed; do
  gcloud run jobs describe "$j" --region="$REGION" >/dev/null && echo "ok: job $j"
done
gcloud sql instances describe cm-pg --format='value(settings.edition,state)'
