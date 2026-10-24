## Why
The web UI needs routes the backend slice lacks: undo a dose, documents, medicines, live updates (SSE), a district view, delivery status, per-item bulk results and person_id on patient rows.

## What Changes
- DELETE /portal/dose (compensating event, idempotent), GET /portal/documents, GET /portal/medicines.
- UiPatient gains person_id.
- POST /review/bulk-decision items gain ok and message (array shape kept).
- GET /stream (SSE, Postgres LISTEN/NOTIFY via migration 0008 triggers), GET /dashboard/district.
- Doctor message list gains delivery (queued, sent, failed) from the outbox row.
- PUT /admin/settings tested incl. version conflict.

## Out of scope
Web changes (adapter is a later task), contracts edits (RFC-S2 appended to cm/contracts/CHANGES.md), AI-runtime files.

## Owning lane
G (Core API) with B seed files. Implements RFC-S1 follow-ups; no frozen contract file edited.
