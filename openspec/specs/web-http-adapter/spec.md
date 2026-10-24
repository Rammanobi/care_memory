# web-http-adapter Specification

## Purpose
TBD - created by archiving change add-web-http-adapter. Update Purpose after archive.

## Requirements

### Requirement: HTTP adapter
The web app SHALL use an HTTP adapter against `VITE_API_BASE` when `VITE_USE_MOCK=false`, and the in-browser mock otherwise.

#### Scenario: Approve in http mode
- **WHEN** the doctor approves a pending item
- **THEN** the UI posts `/review/{approval_id}/decision` with `X-CM-Client: web` and rolls back with a toast if it fails

### Requirement: Real sign-in
The login page SHALL post username and password to `/auth/login` and route by role; the role switcher SHALL appear only in mock mode.

#### Scenario: Session expired
- **WHEN** any call returns 401
- **THEN** the user is sent to the login page

### Requirement: Live updates
The app SHALL refetch on SSE events from `/stream` and fall back to 5 second polling.

#### Scenario: API down
- **WHEN** the API is unreachable
- **THEN** a banner with a Retry button is shown

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
