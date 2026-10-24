#!/usr/bin/env bash
# Secret Manager: create secrets, generate the random ones, grant access PER SECRET (never project-wide).
# Values for external keys are added by you, never on the command line or in the repo:
#   printf %s "$KEY" | gcloud secrets versions add OPENAI_API_KEY --data-file=-
# Needs 10_iam.sh first (service accounts must exist). Run before 20_sql.sh.
set -euo pipefail
source "$(dirname "$0")/vars.sh"

SECRETS="TELEGRAM_BOT_TOKEN TELEGRAM_WEBHOOK_SECRET GMAIL_OAUTH_CLIENT_JSON GMAIL_REFRESH_TOKEN
OPENAI_API_KEY DEEPSEEK_API_KEY LANGSMITH_API_KEY DB_PASSWORD_APP DB_PASSWORD_ENGINE DB_PASSWORD_READER
DB_PASSWORD_ADMIN JWT_SIGNING_KEY PII_MASTER_KEY DEMO_USER_PASSWORDS"
# P1 only (PWA push): add VAPID_PRIVATE_KEY to the list and grant it to cm-worker.

for s in $SECRETS; do
  gcloud secrets create "$s" --replication-policy=user-managed --locations="$REGION" 2>/dev/null || true
done

has_version() { gcloud secrets versions list "$1" --limit=1 --format='value(name)' | grep -q .; }
gen() { # name command-producing-value
  if ! has_version "$1"; then printf %s "$2" | gcloud secrets versions add "$1" --data-file=-; fi
}
gen PII_MASTER_KEY "$(openssl rand -base64 32)"
gen TELEGRAM_WEBHOOK_SECRET "$(openssl rand -hex 16)"
gen JWT_SIGNING_KEY "$(openssl rand -base64 48)"
for db in DB_PASSWORD_APP DB_PASSWORD_ENGINE DB_PASSWORD_READER DB_PASSWORD_ADMIN; do
  gen "$db" "$(openssl rand -hex 24)"
done

grant() { gcloud secrets add-iam-policy-binding "$1" --member="serviceAccount:$2" \
  --role=roles/secretmanager.secretAccessor -q >/dev/null; }
# cm-api
for s in TELEGRAM_WEBHOOK_SECRET OPENAI_API_KEY DEEPSEEK_API_KEY LANGSMITH_API_KEY DB_PASSWORD_APP \
         DB_PASSWORD_READER JWT_SIGNING_KEY DEMO_USER_PASSWORDS PII_MASTER_KEY; do grant "$s" "$SA_API"; done
# cm-worker
for s in TELEGRAM_BOT_TOKEN GMAIL_OAUTH_CLIENT_JSON GMAIL_REFRESH_TOKEN OPENAI_API_KEY DEEPSEEK_API_KEY \
         LANGSMITH_API_KEY DB_PASSWORD_APP DB_PASSWORD_READER PII_MASTER_KEY; do grant "$s" "$SA_WORKER"; done
# cm-jobs (DB_PASSWORD_ADMIN is cm-jobs only: migrations and erasure)
for s in TELEGRAM_BOT_TOKEN GMAIL_OAUTH_CLIENT_JSON GMAIL_REFRESH_TOKEN OPENAI_API_KEY DEEPSEEK_API_KEY \
         LANGSMITH_API_KEY DB_PASSWORD_ENGINE DB_PASSWORD_ADMIN PII_MASTER_KEY; do grant "$s" "$SA_JOBS"; done
echo "30_secrets: done. Still to add by hand: TELEGRAM_BOT_TOKEN, GMAIL_OAUTH_CLIENT_JSON, GMAIL_REFRESH_TOKEN, OPENAI_API_KEY, DEEPSEEK_API_KEY, LANGSMITH_API_KEY, DEMO_USER_PASSWORDS."
