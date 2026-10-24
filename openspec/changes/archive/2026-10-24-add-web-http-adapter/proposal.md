## Why
The web console only ran on an in-browser mock. It must talk to the real FastAPI backend (port 8080) with real sign-in, live updates and honest error states.

## What Changes
- `web/src/api/httpAdapter.ts`: CareApi over fetch (cookie session, X-CM-Client on mutations, api.Problem errors, GET-only retry, 401 goes to login), plus pure mapping functions.
- Adapter chosen by `VITE_USE_MOCK`; MOCK DATA badge only in mock mode.
- Real login form (POST /auth/login), logout in shells, role route guards; role switcher stays in mock mode only.
- Live updates: SSE `/stream` with 5 s polling fallback.
- Offline banner with retry, toast with rollback on failed optimistic updates.
- `web/dev-server/mock-api.mjs` dev-only verification server; vitest tests for mapping.

Out of scope: any change to `cm/`, contracts or root package.json. Owning lane: H1 (web shell, api, auth, realtime). Implements feature_specs/03_dashboards_ux.md section 0.2. No change to cm/contracts/.
