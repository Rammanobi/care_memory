## Why
Patient questions that need a doctor's expertise only appear in the console. The doctor should also get an email so nothing waits unseen.

## What Changes
- New `cm/channels/doctor_notify.py`: `notify_doctor_new_question(...)` and `render_question_email(...)`, plus a guarded test CLI.
- New env names in `.env.example` only: `DOCTOR_NOTIFY_EMAIL`, `DOCTOR_NOTIFY_MODE` (off | dry-run | send, default dry-run), `CONSOLE_BASE_URL`.
- `cm/store/gmail_repo.py`: `doctor_notify_claim` / `doctor_notify_release` (audit_log rows) for idempotency and throttling.
- Email has patient code only, masked excerpt (<= 200 chars), deep link, no AI text, no approve-by-email.

## Out of scope
Calling it from the task handler (plumbing agent), approve-by-email, real sending (owner confirms first), quiet hours.

Owning lane: M (Gmail), integration slice. Spec: new capability `doctor-notify`. No `cm/contracts/` change.
