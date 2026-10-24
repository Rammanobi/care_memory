## Why
Admin usage showed two "Other" rows and drifting numbers; the Admin page had no real channel state; the nightly job could not be triggered from the API; the Patients list said "Approved and sent" while drafts were pending; audit login rows looked duplicated with a frozen time; a Telegram test failed under a developer `.env` and touched the demo patient.

## What Changes
- `/admin/usage`: task rows merged by display name, sorted by spend then name, rounded once (root cause: per-task-type rows with the same name, unordered).
- New `GET /admin/channels` (telegram bot/bindings/recent traffic; gmail and calendar "Not connected" unless configured).
- New `POST /admin/demo/run-nightly` (admin, demo mode) and a `nightly` task handler; fake model unless CM_DATA_CLASS is mock/synthetic, `live` was asked and the governor is not RED.
- Patients next step: pending green-tier drafts count as open.
- Login audit uses real time (sim clock is pinned) and ignores a repeat within 5 s; audit list bound uses the later of sim and real now.
- Telegram tests use throwaway patient P-9901 and force DEMO_IGNORE_QUIET_HOURS=0.

Owning lane: G (cm/api, tests) with B's admin router touched at the owner's request. Out of scope: web/, cm/memory, cm/rules, contracts.

## Verification
`DEMO_IGNORE_QUIET_HOURS=0 pytest -m 'not live and not slow and not docs' tests/unit tests/integration`: 322 passed.
