#!/usr/bin/env bash
# Deploy cm-worker, cm-api and the five Cloud Run Jobs from ONE image, then apply resource-level IAM.
# Usage: IMAGE=$REGION-docker.pkg.dev/$PROJECT/cm/cm:<tag> bash infra/60_deploy.sh
# Cloud Build runs this after the cm-migrate step. First deploy: build and push an image manually first.
set -euo pipefail
source "$(dirname "$0")/vars.sh"
: "${IMAGE:?set IMAGE=<artifact-registry image with tag>}"

COMMON=(--region="$REGION" --image="$IMAGE" --add-cloudsql-instances="$INSTANCE")
s() { echo "$1=$1:latest"; }
join() { local IFS=,; echo "$*"; }
SEC_API=$(join $(s TELEGRAM_WEBHOOK_SECRET) $(s OPENAI_API_KEY) $(s DEEPSEEK_API_KEY) $(s LANGSMITH_API_KEY) \
  $(s DB_PASSWORD_APP) $(s DB_PASSWORD_READER) $(s JWT_SIGNING_KEY) $(s DEMO_USER_PASSWORDS) $(s PII_MASTER_KEY))
SEC_WK=$(join $(s TELEGRAM_BOT_TOKEN) $(s GMAIL_OAUTH_CLIENT_JSON) $(s GMAIL_REFRESH_TOKEN) $(s OPENAI_API_KEY) \
  $(s DEEPSEEK_API_KEY) $(s LANGSMITH_API_KEY) $(s DB_PASSWORD_APP) $(s DB_PASSWORD_READER) $(s PII_MASTER_KEY))
SEC_JOBS=$(join $(s TELEGRAM_BOT_TOKEN) $(s GMAIL_OAUTH_CLIENT_JSON) $(s GMAIL_REFRESH_TOKEN) $(s OPENAI_API_KEY) \
  $(s DEEPSEEK_API_KEY) $(s LANGSMITH_API_KEY) $(s DB_PASSWORD_ENGINE) $(s DB_PASSWORD_ADMIN) $(s PII_MASTER_KEY))

gcloud run deploy cm-worker "${COMMON[@]}" --service-account="$SA_WORKER" --no-allow-unauthenticated \
  --min-instances=0 --max-instances=5 --concurrency=4 --timeout=1800 --cpu=2 --memory=2Gi \
  --env-vars-file=infra/env/worker.env.yaml --set-secrets="$SEC_WK"
WORKER_URL=$(gcloud run services describe cm-worker --region="$REGION" --format='value(status.url)')

gcloud run deploy cm-api "${COMMON[@]}" --service-account="$SA_API" --allow-unauthenticated \
  --min-instances=1 --max-instances=4 --concurrency=40 --timeout=60 --cpu=2 --memory=2Gi --cpu-boost \
  --env-vars-file=infra/env/api.env.yaml --update-env-vars="WORKER_URL=$WORKER_URL" --set-secrets="$SEC_API"
API_URL=$(gcloud run services describe cm-api --region="$REGION" --format='value(status.url)')
gcloud run services update cm-api --region="$REGION" --update-env-vars="PUBLIC_BASE_URL=$API_URL,PUBSUB_PUSH_AUDIENCE=$API_URL/webhooks/gmail"

job() { # name task-timeout cpu memory max-retries
  # UNVERIFIED: combining --env-vars-file with --update-env-vars on `jobs deploy`; fall back to one file per job if rejected.
  gcloud run jobs deploy "$1" --region="$REGION" --image="$IMAGE" --service-account="$SA_JOBS" \
    --set-cloudsql-instances="$INSTANCE" --tasks=1 --parallelism=1 --max-retries="$5" --task-timeout="$2" \
    --cpu="$3" --memory="$4" --env-vars-file=infra/env/jobs.env.yaml \
    --update-env-vars="CM_JOB=${1#cm-},WORKER_URL=$WORKER_URL" --set-secrets="$SEC_JOBS"
}
job cm-migrate 600s  1 1Gi 0
job cm-nightly 3600s 2 4Gi 1
job cm-sweeper 240s  1 1Gi 0
job cm-seed    1800s 2 4Gi 0
job cm-eval    1800s 2 4Gi 0

# Resource-level IAM (I3, I7). run.developer carries run.jobs.runWithOverrides, which run.invoker lacks.
gcloud run services add-iam-policy-binding cm-worker --region="$REGION" \
  --member="serviceAccount:$SA_INVOKER" --role=roles/run.invoker >/dev/null
gcloud run services add-iam-policy-binding cm-api --region="$REGION" \
  --member="serviceAccount:$SA_PUSH" --role=roles/run.invoker >/dev/null
for j in cm-nightly cm-sweeper; do
  gcloud run jobs add-iam-policy-binding "$j" --region="$REGION" \
    --member="serviceAccount:$SA_INVOKER" --role=roles/run.invoker >/dev/null
done
for j in cm-seed cm-eval cm-nightly cm-sweeper; do
  gcloud run jobs add-iam-policy-binding "$j" --region="$REGION" \
    --member="serviceAccount:$SA_API" --role=roles/run.developer >/dev/null
done
echo "60_deploy: api=$API_URL worker=$WORKER_URL"
