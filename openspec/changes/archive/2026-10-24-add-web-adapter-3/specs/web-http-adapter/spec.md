## ADDED Requirements
### Requirement: Live updates over SSE
The web client SHALL listen to GET /stream topics review and channels, refetch immediately on an event, poll every 5 s when SSE is down and every 30 s while connected, reconnect with backoff, and show a live indicator.

#### Scenario: Doctor approves, patient page updates
- **WHEN** an approval is decided and a review event arrives
- **THEN** the client reloads its data without a page reload

### Requirement: Server-backed patient and doctor extras
The client SHALL use DELETE /portal/dose, /portal/documents, /portal/medicines, /dashboard/district and /consents/{person_id}, show message delivery state, and show per-item bulk approve results.

#### Scenario: Suppressed district cell
- **WHEN** a district value is null and listed in suppressed
- **THEN** the cell reads "under 5, hidden"
