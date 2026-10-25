## Why
Behind Firebase Hosting the CDN must never cache PHI, and Cloud Run needs a complete env template.

## What Changes
- `cm/api/no_store.py` ASGI middleware (wired in `cm/api/main.py`): `Cache-Control: private, no-store` on responses to requests carrying `Authorization` or `cm_session`, unless the response sets its own.
- `infra/env/api.env.yaml`: AUTH_MODE, FIREBASE_PROJECT_ID, Hosting CORS_ORIGINS/CM_ALLOWED_HOSTS, Telegram vars (names/placeholders only).
- CORS checked: `Authorization` already allowed; no code change.

Out of scope: web/, docs/, contracts. Lane: G (api) + I (env template). Local behaviour unchanged (AUTH_MODE=local default).
