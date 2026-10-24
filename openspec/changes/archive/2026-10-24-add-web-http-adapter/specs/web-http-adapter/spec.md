## ADDED Requirements

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
