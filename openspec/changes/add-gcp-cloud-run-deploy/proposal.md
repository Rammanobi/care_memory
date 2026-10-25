## Why
There is no deployment path to Cloud Run.

## What Changes
Add Dockerfiles, Cloud Run services (cm-api, cm-sweeper), Cloud Run Jobs (cm-jobs), Cloud Tasks queues agent-runs, resumes, outbound, and a deploy script/doc.

## Out of scope
Provisioning real secrets in repo.

## Owning lane
Infra lane. No change to `cm/contracts/`.

## Update 2026-10-25 (RUNBOOK 1.1-1.6)
Stage 1 targets project `carememory-c1b3f` (asia-south1), Firebase Hosting sites `carememory-doctor` / `carememory-patient`,
`run.app` URLs, no custom domain, no load balancer. Owner decision: the cloud Telegram bot is skipped
(`TELEGRAM_ENABLED=0`; code already tolerates a missing token: outbound rows fail with `auth`, webhook fails closed).
Fixes first-deploy blockers: `*.run.app` host pattern, `CM_TASKS_BASE_URL` on all services, `--env-vars-file` vs
`--update-env-vars`, missing secret grants, `.gcloudignore`, DEMO_USER_PASSWORDS upload without printing. Lane I.
No change to `cm/contracts/` and no application code change.
