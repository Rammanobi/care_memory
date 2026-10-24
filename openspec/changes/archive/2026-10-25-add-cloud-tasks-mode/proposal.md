## Why
`TASKS_MODE=cloud` raised NotImplementedError and `/tasks/*` answered 501, so the Cloud Run deployment could not enqueue or run background work (CLAUDE.md rule 8, INTEGRATION_DECISIONS I11).

## What Changes
- `cm.core.tasks.enqueue` in cloud mode creates a Cloud Tasks HTTP task (name = task_id, OIDC token, schedule delay) through an injectable client; ALREADY_EXISTS counts as success.
- `/tasks/*` in cloud mode verify the Google OIDC JWT (audience CM_TASKS_BASE_URL, email CM_TASKS_SA), fail closed; local mode keeps the admin login.
- New `POST /tasks/run` generic dispatcher (claims `task_runs`, heartbeat, SIGTERM respect, replay-safe) and idempotent `POST /tasks/drain-outbox` for Cloud Scheduler.
- `task_runs_repo.claim/heartbeat/finish` implemented; `cm.jobs.migrate` verified idempotent and non-zero on failure.
- Env names introduced: CM_TASKS_BASE_URL, CM_TASKS_SA, CM_TASKS_QUEUE_AGENT_RUNS, CM_TASKS_QUEUE_RESUMES, CM_TASKS_QUEUE_OUTBOUND (fall back to TASKS_QUEUE_*), GCP_PROJECT and GCP_REGION (existing).

## Out of scope
Real Google Cloud calls, infra scripts, calendar_sync implementation (stub), web/, rag, eval, agents, memory, rules.

## Owning lane
A (core, store, jobs/migrate) with G (api router) and I (requirements). No change to `cm/contracts/`.
