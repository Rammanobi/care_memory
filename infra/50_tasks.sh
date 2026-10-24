#!/usr/bin/env bash
# Cloud Tasks queues (INTEGRATION_DECISIONS I11): agent-runs and resumes 2/s, 4 concurrent, 6 attempts;
# outbound 5/s, 10 concurrent. Size max-concurrent-dispatches <= provider RPM / LLM calls per task.
# Tasks are created with name = task_id for dedupe (cm.core.tasks.enqueue).
set -euo pipefail
source "$(dirname "$0")/vars.sh"

for q in agent-runs resumes; do
  ARGS=(--location="$REGION" --max-dispatches-per-second=2 --max-concurrent-dispatches=4
        --max-attempts=6 --min-backoff=10s --max-backoff=300s --max-doublings=4)
  gcloud tasks queues create "$q" "${ARGS[@]}" 2>/dev/null || gcloud tasks queues update "$q" "${ARGS[@]}"
done
ARGS=(--location="$REGION" --max-dispatches-per-second=5 --max-concurrent-dispatches=10
      --max-attempts=10 --min-backoff=2s --max-backoff=120s)
gcloud tasks queues create outbound "${ARGS[@]}" 2>/dev/null || gcloud tasks queues update outbound "${ARGS[@]}"
echo "50_tasks: done."
