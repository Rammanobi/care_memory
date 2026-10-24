## Why
The finished React UI runs on in-browser mock data. One real vertical slice (database, repos, the single doctor decision function, auth, console and patient-app routes, deterministic seed) lets the UI talk to a real Postgres through a real API. No LLM, Telegram or Gmail.

## What Changes
- Lane A: `cm/core` (config, db pool, clock, ids), `cm/store` repos (events, approvals, outbox, consent, settings), `cm/jobs/migrate.py`.
- Lane G: `cm/review/decide.py` (single decision transaction), `cm/api` (auth, review, requests, dashboard, query, admin, portal routes), uvicorn on port 8080, CORS for http://localhost:5173.
- Lane B: `cm/api/suppress.py` banned-term filter on patient/supporter responses, `cm/jobs/seed.py` (seed 42, the same sample content the UI shows).
- New `cm/api/portal_models.py` for models the frozen contracts lack (patient self-service, slice-level patient list/detail, usage). RFC appended to `cm/contracts/CHANGES.md`. Contracts are not edited.
- Tests: `tests/unit` and `tests/integration` (marker `db`).

Out of scope: LLM calls, Telegram, Gmail, memory engine tables (features, beliefs, risk), real-time stream, templates/erasure routes, web/ changes.
Owning lanes: A, B, G (combined slice). Spec sections: INTEGRATION_DECISIONS a, c, d; feature_specs/03.

## Impact
New backend code only. Contracts untouched (RFC appended).
