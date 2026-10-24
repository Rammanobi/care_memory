#!/usr/bin/env bash
# Secret Manager: create secrets, generate the random ones, grant access PER SECRET (never project-wide).
# Values for external keys are added by you, never on the command line or in the repo:
#   printf %s "$KEY" | gcloud secrets versions add OPENAI_API_KEY --data-file=-
# Secrets with no value yet are fine here; 60_deploy.sh mounts only secrets that have a value.
# REQUIRED names (deploy cannot work without a value): DEEPSEEK_API_KEY OPENAI_API_KEY TELEGRAM_BOT_TOKEN
#   DEMO_USER_PASSWORDS (JSON the seed expects). Auto-generated here: TELEGRAM_WEBHOOK_SECRET JWT_SIGNING_KEY
#   PII_MASTER_KEY DB_PASSWORD_*. OPTIONAL (skipped when empty): LANGSMITH_API_KEY GMAIL_OAUTH_CLIENT_JSON GMAIL_REFRESH_TOKEN.
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

has_version() { has_secret_value "$1"; }
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
REQUIRED_BY_HAND="DEEPSEEK_API_KEY OPENAI_API_KEY TELEGRAM_BOT_TOKEN DEMO_USER_PASSWORDS"
echo "30_secrets: done. Required values still missing (names only):"
missing=0
for s in $REQUIRED_BY_HAND; do
  if ! has_secret_value "$s"; then echo "  MISSING: $s"; missing=1; fi
done
[ "$missing" = 0 ] && echo "  none"
echo "Optional (skipped by 60_deploy.sh until set): LANGSMITH_API_KEY GMAIL_OAUTH_CLIENT_JSON GMAIL_REFRESH_TOKEN"
echo "Add a value with:  printf %s \"\$VALUE\" | gcloud secrets versions add NAME --data-file=-"
