#!/usr/bin/env bash
# Cloud SQL Postgres 16 (cm-pg), database and the four DB roles.
# Run 30_secrets.sh BEFORE this script and add the four DB_PASSWORD_* secret values first.
# Extensions, schemas (cm, lg), pgvector >= 0.7 assert and grants are done by the cm-migrate job, not here.
# Usage: bash infra/20_sql.sh
set -euo pipefail
source "$(dirname "$0")/vars.sh"

# --edition=ENTERPRISE is REQUIRED: PG16 defaults to ENTERPRISE_PLUS, which rejects db-custom-* tiers.
gcloud sql instances create cm-pg --database-version=POSTGRES_16 --edition=ENTERPRISE \
  --tier=db-custom-1-3840 --region="$REGION" --storage-size=10GB --storage-auto-increase \
  --availability-type=zonal --backup-start-time=20:30 --database-flags=max_connections=100 || true
gcloud sql databases create caremem --instance=cm-pg || true

pw() { gcloud secrets versions access latest --secret="$1"; }
for pair in "cm_app:DB_PASSWORD_APP" "cm_engine:DB_PASSWORD_ENGINE" "cm_reader:DB_PASSWORD_READER" "cm_admin:DB_PASSWORD_ADMIN"; do
  user="${pair%%:*}"; secret="${pair##*:}"
  if gcloud sql users list --instance=cm-pg --format='value(name)' | grep -qx "$user"; then
    gcloud sql users set-password "$user" --instance=cm-pg --password="$(pw "$secret")"
  else
    gcloud sql users create "$user" --instance=cm-pg --password="$(pw "$secret")"
  fi
done
echo "20_sql: done. Next: deploy cm-migrate (60_deploy.sh) which creates extensions/schemas/grants."
