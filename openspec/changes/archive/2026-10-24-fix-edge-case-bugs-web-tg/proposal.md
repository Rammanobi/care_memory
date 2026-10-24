## Why
Edge-case tests before the public push (web mapping, Telegram lane, reminders) found one gap: the Telugu spelling of "TB" (టీబీ) was not in the banned-term list, so a patient-facing send containing it was not blocked. Hindi टीबी and Telugu క్షయ were already covered.

## What Changes
- `cm/router/banned.py`: add "టీబీ" to the substring list (lane F).
- New tests only otherwise: `web/src/api/edge.test.ts`, `tests/unit/channels/test_tg_edge.py`, `tests/unit/jobs/test_reminders_edge.py`.

## Details
- Owning lane: F (router). No contract change.
- Symptom: `find_banned("టీబీ")` returned []; the sender and reminder name check let it through.
- Root cause: list had Telugu "క్షయ" only.
- Fix: add the term. Verified by test_tg_edge banned variants and test_reminders_edge odd names.
- Out of scope: tests/unit quiet-hours tests that fail when a dev .env sets DEMO_IGNORE_QUIET_HOURS=1 with CM_ENV=dev (test isolation, not product behaviour).
