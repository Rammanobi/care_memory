#!/usr/bin/env bash
# Cloud Scheduler (time zone Asia/Kolkata). Red escalation is a cm-sweeper duty, not a scheduler task.
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

RUNJOB sched-nightly      "0 1 * * *"     cm-nightly
RUNJOB sched-sweeper      "*/5 * * * *"   cm-sweeper
# Check-in slots (I8). Slot names are an assumption: align with cm/router (CheckinSlot) before demo. UNVERIFIED
TASK   sched-checkins     "30 7 * * *"    /tasks/checkins '{"slot":"morning"}'
TASK   sched-checkins-eve "30 18 * * *"   /tasks/checkins '{"slot":"evening"}'
TASK   sched-checkins-sup "0 19 * * *"    /tasks/checkins '{"slot":"supporter_proxy"}'
TASK   sched-portal-sync  "30 0 * * *"    /tasks/portal-sync
TASK   sched-digest       "0 12 * * *"    /tasks/digest
TASK   sched-visit-lists  "0 17 * * *"    /tasks/visit-lists
TASK   sched-gmail-renew  "0 6 * * *"     /tasks/gmail-watch-renew
TASK   sched-gmail-sweep  "*/30 * * * *"  /tasks/gmail-sweep
# P1 (not created): /tasks/calendar-sync after nightly; monthly /tasks/district-report
echo "70_scheduler: done."
