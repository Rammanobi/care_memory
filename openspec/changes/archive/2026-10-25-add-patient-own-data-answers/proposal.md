## Why
Patients ask simple questions about their own record (doses this week, streak, next visit, last refill). Answering them instantly from code removes doctor load and needs no model.

## What Changes
- `GET /portal/answers` (patient role only): answer cards computed from `cm.memory.features` and the events store at `clock.now()`, rendered through approved templates (EN and TE, `cm/router/templates/own_data.yaml`).
- New files: `cm/api/own_data.py`, `cm/api/routers/portal_answers.py` (one-line include in `cm/api/main.py`), `AnswerCard` in `cm/api/portal_models.py`.
- Fewer than 3 check-ins: one "not enough history" card replaces the dose cards. Fixed advice footer card points to the care team.

Out of scope: Telegram, any model call, Supporter access (supporter routes are limited to the week strip under sharing consent), web UI (separate agent). Owning lane: G (content templates K). No `cm/contracts/` change. Spec: patient-app.
