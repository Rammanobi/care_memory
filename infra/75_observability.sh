#!/usr/bin/env bash
# STUB (P1, feature spec 04 F7): log-based metrics (task_runs_by_state, spend, errors) and alert policies
# from infra/metrics/*.yaml and infra/alerts/*.yaml. Those YAML files do not exist yet.
# Usage: bash infra/75_observability.sh
set -euo pipefail
source "$(dirname "$0")/vars.sh"
shopt -s nullglob
for f in "$(dirname "$0")"/metrics/*.yaml; do
  name="$(basename "$f" .yaml)"
  gcloud logging metrics create "$name" --config-from-file="$f" 2>/dev/null \
    || gcloud logging metrics update "$name" --config-from-file="$f"
done
for f in "$(dirname "$0")"/alerts/*.yaml; do
  gcloud alpha monitoring policies create --policy-from-file="$f" || true
done
echo "75_observability: done (no-op if metrics/ and alerts/ are empty)."
