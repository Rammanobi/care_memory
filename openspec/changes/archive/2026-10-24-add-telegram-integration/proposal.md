## Why
The Telegram lane (lane F) was built against fakes. The owner needs a real bot to work once a token is in `.env`.

## What Changes
- Postgres adapters for the lane-F ports, real httpx Telegram client, `POST /webhooks/telegram`.
- Outbox drainer, daily check-in producer, invite script, setWebhook script.
- Local in-process task queue (`TASKS_MODE=local`, dev only; cloud mode is a stub).
- DB-backed budget governor store installed at API startup; `GET /admin/usage/caps`.
- Fast path: 3 missed days in 3 days, or a danger symptom, raises a Red approval draft with a fixed message (no LLM).

Out of scope: Cloud Tasks, agent intake of taps and free text, onboarding wizard. Owning lane: Integration (touches F, G, A files per the coordinator's brief). Implements the Telegram sections of INTEGRATION_DECISIONS. No change to `cm/contracts/`.
