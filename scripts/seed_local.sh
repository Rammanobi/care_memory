#!/usr/bin/env bash
# STUB: bring up local Postgres, migrate, and seed the demo cohort (seed 42, 40 patients, 60 days, frozen at day 59).
# Usage: bash scripts/seed_local.sh [--reset]    (--reset drops the volume first)
# Depends on cm.jobs.migrate and cm.jobs.seed (lanes A and B); fails until they exist.
set -euo pipefail
[ "${1:-}" = "--reset" ] && docker compose down -v
docker compose up -d db
until docker compose exec -T db pg_isready -U postgres -d caremem >/dev/null 2>&1; do sleep 1; done
python -m cm.jobs.migrate
python -m cm.jobs.seed --seed 42 --patients 40 --days 60 --backfill --sim-day 59
echo "seeded. Next: make run-local  (or make snapshot to save fixtures/snapshots/seed42_d59.dump)"
