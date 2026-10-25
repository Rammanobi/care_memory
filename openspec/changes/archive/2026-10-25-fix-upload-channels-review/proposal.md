## Why
Independent review of the upload channels (lanes F and M). Symptoms and root causes:
- HIGH: `gmail_attach.dispatch` sent every message with attachments to the upload lane, never to `on_reply`; an inline logo made a doctor's APPROVE reply ignored. Fix: reply-like mail always goes to `on_reply`, attachments run in addition; inline/tiny images dropped in `gmail._attachments`.
- MEDIUM: Telegram files (up to 10 MB) were downloaded inside the webhook request. Fix: webhook path acks and enqueues task `tgfile-<file_unique_id>` (queue agent-runs, handler in `cm/api/routers/tasks.py`); the poller (`handle_local_poll`, `Deps.inline_files=True`) keeps inline download.
- MEDIUM: download happened before token lookup, origin dedupe and rate limit. Fix: those run first.
- LOW: `PT-906` matched and failed the token CHECK (now exactly 4 digits, answered `no_patient_code`); hard-coded 10 MB replaced by `cm.uploads.validate.max_bytes()` with fallback.
- Not fixed: author_role for gmail uploads (intake has no such argument).

## What Changes
Lane F (`tg_upload.py`, `tg_inbound.py` Deps field, `telegram.py` one-line poll flag) and lane M (`gmail_attach.py`, `gmail.py`), `cm/api/routers/tasks.py` (tgfile handler), `NOTES_gmail.md`, and the spec wording (library path, not wired). Out of scope: `cm/uploads/*`, portal, web. No contract change.

## Verification
`pytest tests/unit/gmail tests/unit/channels`: 149 passed (new tests for each fix).
