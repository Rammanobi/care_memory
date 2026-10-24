## Why
Production needs ONE container that serves the API and the web console, working on any hostname, with no secrets baked in. The old Dockerfile copied directories that do not exist, had no `cm/__main__.py` entrypoint, built the web app against `http://localhost:8080`, and the API did not serve the web app.

## What Changes
- Multi-stage `Dockerfile`: node builds `web/` with `VITE_USE_MOCK=false` and an empty (same-origin) `VITE_API_BASE`; python runtime copies `web/dist`; non-root uid 10001; `HEALTHCHECK` on `/healthz`; honours `$PORT`.
- New `cm/__main__.py` (`CM_ROLE=api|worker|job`), uvicorn with graceful SIGTERM drain.
- New `cm/api/web.py`: static files plus SPA fallback registered after all API routes; immutable cache for `/assets/*`, `no-cache` for `index.html`; `CM_ALLOWED_HOSTS` Host validation (`/healthz`, `/readyz` exempt).
- `cm/core/config.py` + `cm/api/routers/auth.py`: `CM_COOKIE_DOMAIN`, Secure cookie when `CM_ENV=prod`.
- `web/src/api/http.ts`: an empty API base resolves against `location.origin`.
- `.dockerignore` excludes `.env*`, `out/`, `node_modules`, dumps; `.env.example` lists the new names.
- Tests: `tests/integration/test_web_serving.py` (caremem_test).

## Out of scope
Google Cloud deploy, pushing the image, DNS/TLS, `infra/60_deploy.sh` and `cloudbuild.yaml` changes (they already build and deploy this one image).

## Owning lane
I (Infra) for Dockerfile, `.dockerignore`, `.env.example`; G (Core API) for `cm/api/*`; A for `cm/core/config.py` (two additive fields); H1 for the one-line `http.ts` change, all done at the owner's request. No contracts touched. Implements INTEGRATION_DECISIONS single-image deploy.
