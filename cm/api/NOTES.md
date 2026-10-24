# Backend slice 1: notes (lanes A, B, G)

Run (from caremem/, Git Bash or PowerShell):
- `docker compose up -d db` (host port from `DB_PORT` in .env; 5433 here because another Postgres owns 5432)
- `python -m cm.jobs.migrate`  then  `python -m cm.jobs.seed --reset`  (`--small` for 6 patients)
- `python -m uvicorn cm.api.main:app --port 8080`
- `python -m pytest -m "not live and not slow and not docs"` (db tests use database `caremem_test`, created on demand)

Verified: migrations 0001..0007, seed twice (no duplicates), curl of all routes, 41 tests.
Known gaps: templates write routes, erasure routes, channels/sim/eval routers,
PII vault encryption, memory engine (UI patient rows come from `ContextNote{kind:'summary'}`), outbox sending
(router/drainer), resume tasks (no graph runtime). See contracts/CHANGES.md RFC-S1.
Demo logins: usernames dr.rao, admin.demo, ravi.pt0142, lakshmi.s01; passwords are in `.env` DEMO_USER_PASSWORDS.

## Gaps slice 1 (RFC-S2, change add-backend-gaps-1)
New routes: `DELETE /portal/dose`, `GET /portal/documents`, `GET /portal/medicines`, `GET /stream`,
`GET /dashboard/district`. Extended: `UiPatient.person_id`, `MessageOut.delivery`, `/review/bulk-decision` items
(`ok`, `error_code`, `message`), `PUT /admin/settings` (version + 409 `version_conflict`, tested).
Stream: Postgres LISTEN/NOTIFY on `cm_events` (migration 0008), one connection and thread per open stream.
Commands: `python -m cm.jobs.migrate`, `python -m cm.jobs.seed --reset`,
`curl -N -b cookies.txt "localhost:8080/stream?topics=review,channels"`,
`python -m pytest tests/integration/test_gaps1.py`.
Rough edges fixed: same-instant dose edits tied on time (superseded rows are now skipped); bulk-decision mapped
unknown errors to `not_found` (now passes the real code).
