## Why
The doctor flow ran on the real API but the patient and Supporter screens, the doctor Ask page, the patient Timeline tab, bulk approve and server settings still used sample data or local mocks when `VITE_USE_MOCK=false`.

## What Changes
- Patient and Supporter screens read /portal/me, /portal/today, /portal/record, /portal/inbox, /portal/requests, /portal/consents and /portal/supporter/checkin; writes go to /portal/dose, /portal/requests, /portal/reminder-request, /portal/consents (PUT) and /portal/messages/{id}/read. New `usePortal` hook keeps mock mode unchanged.
- Patient extras in localStorage keep only UI prefs in http mode (large text, welcome done); consents, reminder and read state come from the server.
- Doctor Ask uses POST /query and /query/suggestions (number badge = `numbers_verified`); Timeline tab uses /patients/{pid}/timeline; bulk approve uses /review/bulk-decision with single-post fallback; Settings shows the /admin/settings version.
- New mappers with vitest tests. Polling stays at 5 s; SSE fallback code unchanged.

Out of scope: any change to `cm/`. Owning lane: H1/H2 (web). Implements feature_specs/03_dashboards_ux.md section 0.2. No change to cm/contracts/.
Gaps left for the backend owner: dose undo, medicine names list, documents, person_id for /consents/{person_id}, settings write UI.
