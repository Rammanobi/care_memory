#!/usr/bin/env bash
# Shared variables. Every infra script does: set -euo pipefail; source "$(dirname "$0")/vars.sh"
# Override PROJECT/REGION/DOMAIN in the environment before running if needed.
# DRY_RUN=1 turns every gcloud call into a printed line (no network, nothing executed); safe to try anywhere.
export PROJECT="${PROJECT:-caremem-hack}"
export REGION="${REGION:-asia-south1}"
export DOMAIN="${DOMAIN:-}"   # apex domain, e.g. example.org (no scheme). Needed by 60/85/90.
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

# render_env <yaml>: print path of a temp copy with <domain> replaced by $DOMAIN (needs DOMAIN if placeholders exist).
render_env() {
  local out; out="$(mktemp)"
  if grep -q '<domain>' "$1"; then need_domain; fi
  sed "s/<domain>/$DOMAIN/g" "$1" > "$out"
  echo "$out"
}

# has_secret_value <name>: true when the secret exists and has at least one version (never reads the value).
has_secret_value() {
  [ "$DRY_RUN" = "1" ] && return 0
  gcloud secrets versions list "$1" --limit=1 --format='value(name)' 2>/dev/null | grep -q .
}
