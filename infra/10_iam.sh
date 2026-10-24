#!/usr/bin/env bash
# Six service accounts and their project/bucket-level roles. Per-secret grants are in 30_secrets.sh;
# resource-level run.invoker/run.developer bindings are in 60_deploy.sh (they need deployed resources).
# Usage: bash infra/10_iam.sh   (needs 00_project.sh first)
set -euo pipefail
source "$(dirname "$0")/vars.sh"

for sa in cm-api cm-worker cm-jobs cm-tasks-invoker cm-pubsub-push cm-deployer; do
  gcloud iam service-accounts create "$sa" --display-name="$sa" || true
done

proj() { gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$1" --role="$2" --condition=None -q >/dev/null; }

# runtime SAs: Cloud SQL, enqueue Cloud Tasks, and act as the invoker SA (all three enqueue OIDC tasks; I2)
for sa in $SA_API $SA_WORKER $SA_JOBS; do
  proj "$sa" roles/cloudsql.client
  proj "$sa" roles/cloudtasks.enqueuer
  gcloud iam service-accounts add-iam-policy-binding "$SA_INVOKER" --member="serviceAccount:$sa" \
    --role=roles/iam.serviceAccountUser -q >/dev/null
done
proj "$SA_JOBS" roles/cloudtasks.queueAdmin      # sweeper pauses agent-runs on spend cap

# docs bucket (I4)
for sa in $SA_API $SA_WORKER $SA_JOBS; do
  gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$sa" \
    --role=roles/storage.objectAdmin >/dev/null
done

# deployer (Cloud Build runs as this SA; runs cm-migrate and deploys)
proj "$SA_DEPLOY" roles/run.admin
proj "$SA_DEPLOY" roles/artifactregistry.writer
proj "$SA_DEPLOY" roles/logging.logWriter
proj "$SA_DEPLOY" roles/cloudsql.client
for sa in $SA_API $SA_WORKER $SA_JOBS; do
  gcloud iam service-accounts add-iam-policy-binding "$sa" --member="serviceAccount:$SA_DEPLOY" \
    --role=roles/iam.serviceAccountUser -q >/dev/null
done

# Pub/Sub service agent: mint OIDC tokens for the push SA (needed on pre-2021 projects; harmless otherwise)
gcloud iam service-accounts add-iam-policy-binding "$SA_PUSH" --member="serviceAccount:$PUBSUB_AGENT" \
  --role=roles/iam.serviceAccountTokenCreator -q >/dev/null || echo "WARN: Pub/Sub service agent not provisioned yet; rerun after 40_pubsub.sh"
echo "10_iam: done."
