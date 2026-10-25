#!/usr/bin/env bash
# Shared variables. Every infra script does: set -euo pipefail; source "$(dirname "$0")/vars.sh"
# Override PROJECT/REGION/DOCTOR_SITE/PATIENT_SITE/DOMAIN in the environment before running if needed.
# DRY_RUN=1 turns every gcloud call into a printed line (no network, nothing executed); safe to try anywhere.
# This is the ONE place for the project id and the two Firebase Hosting site ids: infra/env/*.env.yaml use the
# placeholders <project>, <doctor-site>, <patient-site>, which render_env fills from here. (.firebaserc and
# infra/cloudbuild.yaml cannot source this file; they hold the same literal values.)
export PROJECT="${PROJECT:-carememory-c1b3f}"
export REGION="${REGION:-asia-south1}"
export DOCTOR_SITE="${DOCTOR_SITE:-carememory-doctor}"    # https://$DOCTOR_SITE.web.app
export PATIENT_SITE="${PATIENT_SITE:-carememory-patient}"  # https://$PATIENT_SITE.web.app
export DOMAIN="${DOMAIN:-}"   # optional apex custom domain (stage 2, LB only: 85_lb.sh). Stage 1 uses *.web.app + run.app.
# Cloud Telegram bot: OFF by default (owner decision 2026-10-25). TELEGRAM_ENABLED=1 restores the bot token
# secret, the webhook secret and the setWebhook step (80/90).
export TELEGRAM_ENABLED="${TELEGRAM_ENABLED:-0}"
export DRY_RUN="${DRY_RUN:-0}"

if [ "$DRY_RUN" = "1" ]; then
  gcloud() { echo "[dry-run] gcloud $*" >&2; }
  curl() { echo "[dry-run] curl <args hidden>" >&2; }
fi

export PN="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)' 2>/dev/null || true)"
export AR="$REGION-docker.pkg.dev/$PROJECT/cm"
export INSTANCE="$PROJECT:$REGION:cm-pg"
export SA_API="cm-api@$PROJECT.iam.gserviceaccount.com"
export SA_WORKER="cm-worker@$PROJECT.iam.gserviceaccount.com"
export SA_JOBS="cm-jobs@$PROJECT.iam.gserviceaccount.com"
export SA_INVOKER="cm-tasks-invoker@$PROJECT.iam.gserviceaccount.com"
export SA_PUSH="cm-pubsub-push@$PROJECT.iam.gserviceaccount.com"
export SA_DEPLOY="cm-deployer@$PROJECT.iam.gserviceaccount.com"
export BUCKET="$PROJECT-cm-docs"
export PUBSUB_AGENT="service-$PN@gcp-sa-pubsub.iam.gserviceaccount.com"

# Hostnames served by the LB: apex, doctor., patient., family., demo.
hosts() { echo "$DOMAIN doctor.$DOMAIN patient.$DOMAIN family.$DOMAIN demo.$DOMAIN"; }
need_domain() { [ -n "$DOMAIN" ] || { echo "set DOMAIN=<your apex domain>" >&2; exit 1; }; }

# render_env <yaml> [KEY=VALUE ...]: print the path of a temp copy with <project>, <region>, <doctor-site>,
# <patient-site> (and <domain>, only if present: needs DOMAIN) filled in, plus each KEY=VALUE appended as
# `KEY: "VALUE"`. One file per deploy, so --env-vars-file is never combined with --update-env-vars.
# Exits if any <placeholder> is left. Values must be non-secret (secrets go through --set-secrets).
render_env() {
  local src="$1" out kv; shift
  out="$(mktemp)"
  if grep -q '<domain>' "$src"; then need_domain; fi
  sed -e "s/<project>/$PROJECT/g" -e "s/<region>/$REGION/g" -e "s/<doctor-site>/$DOCTOR_SITE/g" \
      -e "s/<patient-site>/$PATIENT_SITE/g" -e "s/<domain>/$DOMAIN/g" "$src" > "$out"
  for kv in "$@"; do printf '%s: "%s"\n' "${kv%%=*}" "${kv#*=}" >> "$out"; done
  if grep -v '^[[:space:]]*#' "$out" | grep -q '<[a-z-]*>'; then
    echo "render_env: unfilled placeholder in $src" >&2; rm -f "$out"; exit 1
  fi
  echo "$out"
}

# has_secret_value <name>: true when the secret exists and has at least one version (never reads the value).
has_secret_value() {
  [ "$DRY_RUN" = "1" ] && return 0
  gcloud secrets versions list "$1" --limit=1 --format='value(name)' 2>/dev/null | grep -q .
}
