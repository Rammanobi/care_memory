## Why
DEPLOY_PLAN blockers B1 (entrypoint), B4 (Cloud SQL socket DSN, env names the code does not read), B6 (model placeholders, failing optional secrets), B7 (scheduler targets that 404), quiet-hours gate ignored `CM_ENV=demo`, and missing LB, project-API and Telegram webhook scripts.

## What Changes
- `cm/__main__.py`: `python -m cm <api|worker|migrate|drain-outbox|sweeper|nightly|reminders|seed|eval>`; sweeper is a stub exiting 0.
- `cm/core/config.py`: DSN supports `/cloudsql/<instance>` host, `CLOUD_SQL_INSTANCE`, quotes values.
- `cm/router/quiet_hours.py`: override honoured for `CM_ENV` in dev or demo (never prod).
- infra: env YAMLs use `DB_HOST`/`DB_USER`, real model names, COOKIE_SECURE/CORS/hosts; 00/30/60/70/80 fixed; new `85_lb.sh`, `90_telegram_webhook.sh`, `README.md`; `vars.sh` gains DRY_RUN.

Out of scope: Dockerfile, main.py, tasks.py (other agents). Lane I (infra) with small A/F touches. No GCP call was made.
Verified: `pytest tests/unit` (DEMO_IGNORE_QUIET_HOURS=0), `bash -n` on all scripts, DRY_RUN runs.
