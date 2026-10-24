#!/usr/bin/env bash
# Project setup: APIs, Artifact Registry, docs bucket. Idempotent. Billing + budget are manual (console).
# Usage: PROJECT=caremem-hack bash infra/00_project.sh
set -euo pipefail
source "$(dirname "$0")/vars.sh"

gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  sqladmin.googleapis.com secretmanager.googleapis.com cloudscheduler.googleapis.com cloudtasks.googleapis.com \
  pubsub.googleapis.com gmail.googleapis.com calendar-json.googleapis.com iam.googleapis.com \
  iamcredentials.googleapis.com logging.googleapis.com monitoring.googleapis.com storage.googleapis.com

gcloud artifacts repositories create cm --repository-format=docker --location="$REGION" || true

# One docs bucket (INTEGRATION_DECISIONS I4): uploads/lab/, uploads/csv/, raw/, guidelines/
gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access \
  --public-access-prevention || true
LIFECYCLE="$(mktemp)"
cat > "$LIFECYCLE" <<JSON
{"rule":[{"action":{"type":"Delete"},"condition":{"age":30,"matchesPrefix":["uploads/"]}}]}
JSON
gcloud storage buckets update "gs://$BUCKET" --lifecycle-file="$LIFECYCLE"
rm -f "$LIFECYCLE"
echo "00_project: done. Manual: link billing and create a budget (alerts at INR 2,000 / 5,000)."
