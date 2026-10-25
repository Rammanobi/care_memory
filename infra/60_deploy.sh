#!/usr/bin/env bash
# Deploy cm-worker, cm-api and the Cloud Run Jobs (cm-migrate, cm-seed) from ONE image, then apply resource-level IAM.
# Usage: IMAGE=$REGION-docker.pkg.dev/$PROJECT/cm/cm:<tag> bash infra/60_deploy.sh
# Cloud Build runs this after the cm-migrate step. First deploy: build and push an image manually first.
set -euo pipefail
source "$(dirname "$0")/vars.sh"
: "${IMAGE:?set IMAGE=<artifact-registry image with tag>}"

COMMON=(--region="$REGION" --image="$IMAGE" --add-cloudsql-instances="$INSTANCE")
join() { local IFS=,; echo "$*"; }
# sec <ENV_NAME> [SECRET_NAME]: emits ENV=SECRET:latest only when the secret has a value (a secret with no
# version makes `gcloud run deploy` fail). Skipped optional secrets are listed on stderr, names only.
sec() {
  local env="$1" name="${2:-$1}"
  if has_secret_value "$name"; then echo "$env=$name:latest"; else echo "skip secret (no value): $name" >&2; fi
}
# DB password: the code reads DB_PASSWORD; api/worker use cm_app, jobs use cm_admin (DB_USER is in the env YAMLs).
# Telegram secrets are mounted only when TELEGRAM_ENABLED=1 (cloud bot is off by default; see vars.sh).
TG_API=""; TG_WK=""
if [ "$TELEGRAM_ENABLED" = "1" ]; then TG_API="$(sec TELEGRAM_WEBHOOK_SECRET)"; TG_WK="$(sec TELEGRAM_BOT_TOKEN)"; fi
SEC_API=$(join $TG_API $(sec OPENAI_API_KEY) $(sec DEEPSEEK_API_KEY) $(sec LANGSMITH_API_KEY)   $(sec DB_PASSWORD DB_PASSWORD_APP) $(sec JWT_SIGNING_KEY) $(sec DEMO_USER_PASSWORDS) $(sec PII_MASTER_KEY))
SEC_WK=$(join $TG_WK $(sec GMAIL_OAUTH_CLIENT_JSON) $(sec GMAIL_REFRESH_TOKEN) $(sec OPENAI_API_KEY)   $(sec DEEPSEEK_API_KEY) $(sec LANGSMITH_API_KEY) $(sec DB_PASSWORD DB_PASSWORD_APP) $(sec JWT_SIGNING_KEY)   $(sec PII_MASTER_KEY))
SEC_JOBS=$(join $TG_WK $(sec OPENAI_API_KEY) $(sec DEEPSEEK_API_KEY) $(sec LANGSMITH_API_KEY)   $(sec DB_PASSWORD DB_PASSWORD_ADMIN) $(sec JWT_SIGNING_KEY) $(sec DEMO_USER_PASSWORDS) $(sec PII_MASTER_KEY))
# --set-secrets with an empty list is rejected by gcloud; pass the flag only when there is something to mount.
secflag() { [ -n "$1" ] && echo "--set-secrets=$1" || true; }
TMP_ENVS=()
trap 'rm -f "${TMP_ENVS[@]}"' EXIT
# Each deploy gets ONE rendered env file (YAML + appended KEY=VALUE). gcloud rejects --env-vars-file together
# with --update-env-vars, so URLs are written into the file instead (RUNBOOK gaps 2, 15).
# Callers run it in $(...), so they add the path to TMP_ENVS themselves (for the EXIT cleanup).
envfile() { render_env "$@"; }

# cm-worker first: its URL is the Cloud Tasks target and OIDC audience (CM_TASKS_BASE_URL) for everyone.
# First deploy only: the service does not exist yet, so bootstrap it once without the URLs to learn its URL.
WORKER_URL=$(gcloud run services describe cm-worker --region="$REGION" --format='value(status.url)' 2>/dev/null || true)
if [ -z "$WORKER_URL" ] && [ "$DRY_RUN" != "1" ]; then
  ENV_WK=$(envfile infra/env/worker.env.yaml); TMP_ENVS+=("$ENV_WK")
  gcloud run deploy cm-worker "${COMMON[@]}" --service-account="$SA_WORKER" --no-allow-unauthenticated \
    --min-instances=0 --max-instances=5 --concurrency=4 --timeout=1800 --cpu=2 --memory=2Gi \
    --env-vars-file="$ENV_WK" $(secflag "$SEC_WK")
  WORKER_URL=$(gcloud run services describe cm-worker --region="$REGION" --format='value(status.url)')
fi
[ "$DRY_RUN" = "1" ] && WORKER_URL="https://cm-worker-dryrun.$REGION.run.app"
[ -n "$WORKER_URL" ] || { echo "60_deploy: could not read the cm-worker URL" >&2; exit 1; }
# Deploy the worker with its own URL in the single env file (no --update-env-vars mixed with --env-vars-file).
ENV_WK=$(envfile infra/env/worker.env.yaml "WORKER_URL=$WORKER_URL" "CM_TASKS_BASE_URL=$WORKER_URL"); TMP_ENVS+=("$ENV_WK")
gcloud run deploy cm-worker "${COMMON[@]}" --service-account="$SA_WORKER" --no-allow-unauthenticated \
  --min-instances=0 --max-instances=5 --concurrency=4 --timeout=1800 --cpu=2 --memory=2Gi \
  --env-vars-file="$ENV_WK" $(secflag "$SEC_WK")

ENV_API=$(envfile infra/env/api.env.yaml "WORKER_URL=$WORKER_URL" "CM_TASKS_BASE_URL=$WORKER_URL"); TMP_ENVS+=("$ENV_API")
gcloud run deploy cm-api "${COMMON[@]}" --service-account="$SA_API" --allow-unauthenticated \
  --min-instances=1 --max-instances=4 --concurrency=40 --timeout=60 --cpu=2 --memory=2Gi --cpu-boost \
  --env-vars-file="$ENV_API" $(secflag "$SEC_API")
API_URL=$(gcloud run services describe cm-api --region="$REGION" --format='value(status.url)')
[ "$DRY_RUN" = "1" ] && API_URL="https://cm-api-dryrun.$REGION.run.app"
# PUBLIC_BASE_URL stays the patient Hosting site; only the Pub/Sub audience needs the run.app URL.
# `services update --update-env-vars` alone (no --env-vars-file in the same call) is valid and merges.
gcloud run services update cm-api --region="$REGION" --update-env-vars="PUBSUB_PUSH_AUDIENCE=$API_URL/webhooks/gmail"

job() { # name task-timeout cpu memory max-retries
  local envf; envf=$(envfile infra/env/jobs.env.yaml "CM_JOB=${1#cm-}" "WORKER_URL=$WORKER_URL" \
    "CM_TASKS_BASE_URL=$WORKER_URL"); TMP_ENVS+=("$envf")
  gcloud run jobs deploy "$1" --region="$REGION" --image="$IMAGE" --service-account="$SA_JOBS" \
    --set-cloudsql-instances="$INSTANCE" --tasks=1 --parallelism=1 --max-retries="$5" --task-timeout="$2" \
    --cpu="$3" --memory="$4" --env-vars-file="$envf" $(secflag "$SEC_JOBS")
}
job cm-migrate 600s  1 1Gi 0
job cm-seed    1800s 2 4Gi 0
# Later (jobs exist in code but have no demo schedule yet): cm-nightly needs `--args=--patient=<code>`,
# cm-sweeper is a stub, cm-eval is manual. Uncomment when needed:
# job cm-nightly 3600s 2 4Gi 1
# job cm-sweeper 240s  1 1Gi 0
# job cm-eval    1800s 2 4Gi 0

# Resource-level IAM (I3, I7). run.developer carries run.jobs.runWithOverrides, which run.invoker lacks.
gcloud run services add-iam-policy-binding cm-worker --region="$REGION" \
  --member="serviceAccount:$SA_INVOKER" --role=roles/run.invoker >/dev/null
gcloud run services add-iam-policy-binding cm-api --region="$REGION" \
  --member="serviceAccount:$SA_PUSH" --role=roles/run.invoker >/dev/null
for j in cm-seed; do  # add cm-nightly cm-sweeper cm-eval here when those jobs are deployed
  gcloud run jobs add-iam-policy-binding "$j" --region="$REGION" \
    --member="serviceAccount:$SA_API" --role=roles/run.developer >/dev/null
done
echo "60_deploy: api=$API_URL worker=$WORKER_URL"
