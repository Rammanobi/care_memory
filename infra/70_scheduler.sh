#!/usr/bin/env bash
# Cloud Scheduler (time zone Asia/Kolkata). Only targets routes that exist today.
# In demo mode pause the wall-clock ones on stage: gcloud scheduler jobs pause sched-checkins --location=$REGION
# Usage: bash infra/70_scheduler.sh  (after 60_deploy.sh)
set -euo pipefail
source "$(dirname "$0")/vars.sh"
WORKER_URL=$(gcloud run services describe cm-worker --region="$REGION" --format='value(status.url)')
OIDC=(--oidc-service-account-email="$SA_INVOKER" --oidc-token-audience="$WORKER_URL")

RUNJOB() { # name cron job
  gcloud scheduler jobs create http "$1" --location="$REGION" --schedule="$2" --time-zone=Asia/Kolkata \
    --uri="https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/$3:run" --http-method=POST \
    --oauth-service-account-email="$SA_INVOKER" 2>/dev/null \
  || gcloud scheduler jobs update http "$1" --location="$REGION" --schedule="$2" --time-zone=Asia/Kolkata \
    --uri="https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/$3:run" --http-method=POST \
    --oauth-service-account-email="$SA_INVOKER"
}
TASK() { # name cron path [json-body]
  local body="${4:-}"; [ -n "$body" ] || body='{}'
  gcloud scheduler jobs create http "$1" --location="$REGION" --schedule="$2" --time-zone=Asia/Kolkata \
    --uri="$WORKER_URL$3" --http-method=POST --headers=Content-Type=application/json --message-body="$body" \
    "${OIDC[@]}" --attempt-deadline=900s 2>/dev/null \
  || gcloud scheduler jobs update http "$1" --location="$REGION" --schedule="$2" --time-zone=Asia/Kolkata \
    --uri="$WORKER_URL$3" --http-method=POST --headers=Content-Type=application/json --message-body="$body" \
    "${OIDC[@]}" --attempt-deadline=900s
}

# Routes that exist in cm/api/routers/tasks.py: /tasks/drain-outbox, /tasks/checkins (+ /tasks/run, not scheduled).
TASK   sched-drain-outbox "* * * * *"   /tasks/drain-outbox
TASK   sched-checkins     "30 7 * * *"  /tasks/checkins
# OPTIONAL: nightly belief refresh. Needs the cm-nightly job (commented out in 60_deploy.sh; it takes
# `--patient`, so it is not useful as a bare schedule yet). Enable with OPTIONAL_NIGHTLY=1 once deployed.
if [ "${OPTIONAL_NIGHTLY:-0}" = "1" ]; then RUNJOB sched-nightly "0 1 * * *" cm-nightly; fi
# REMOVED (target routes/code do not exist yet): sweeper (stub), checkins-eve/-sup, portal-sync, digest,
# visit-lists, gmail-watch-renew, gmail-sweep, calendar-sync, district-report.
echo "70_scheduler: done. Demo night: DEMO_IGNORE_QUIET_HOURS=1 on cm-api AND cm-worker (CM_ENV=demo)."
