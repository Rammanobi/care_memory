## Why
Backend slice RFC-S2 (add-backend-gaps-1) added undo-dose, documents, medicines, district, consent by person_id, delivery state, bulk results and an SSE stream. The web adapter must use them.

## What Changes
- Patient: Undo dose (DELETE /portal/dose), Documents tab (server list, summary on open), Medicines card from /portal/medicines (empty state when none).
- Doctor: District from /dashboard/district (small cells shown as "under 5, hidden"), consent overview from /consents/{person_id}, delivery chip on sent messages, per-item bulk approve results dialog.
- Live: SSE topics review and channels trigger immediate refetch; polling 5 s fallback, 30 s while connected; reconnect with backoff; live dot (demo in mock mode).
- Tests: mappers and SSE handling with a fake EventSource.

Out of scope: backend, cm/contracts. Lane: web. Implements feature_specs/03_dashboards_ux.md live updates.
