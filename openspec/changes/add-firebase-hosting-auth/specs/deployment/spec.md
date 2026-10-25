## ADDED Requirements

### Requirement: Firebase Hosting sites per audience
The system SHALL serve the built web app from separate Firebase Hosting sites (doctor, patient, family, optional demo) in the Firebase project that shares the Cloud Run project, each landing on its area, rewriting every API route prefix to the Cloud Run service `cm-api`, and falling back to `/index.html` for client routes.

#### Scenario: Doctor site lands on the console
- **WHEN** a browser opens the doctor site root
- **THEN** it is redirected to `/doctor` and the SPA loads

#### Scenario: API call through a Hosting rewrite
- **WHEN** the web app calls `GET /patients` on any site
- **THEN** Hosting forwards the request to `cm-api` and returns its JSON response with `Cache-Control: private, no-store`

#### Scenario: Deep link reload
- **WHEN** a user reloads `/doctor/approvals`
- **THEN** Hosting returns `index.html`, not 404

#### Scenario: Internal routes are not exposed through Hosting
- **WHEN** a request for `/tasks/run` or `/webhooks/telegram` reaches a Hosting site
- **THEN** it is not rewritten to `cm-api` (those routes are reached only on the Cloud Run URL)

### Requirement: Live updates without Hosting streaming
The web app SHALL NOT open `/stream` through a Hosting rewrite; it SHALL poll, or read the SSE stream with a bearer token directly from the Cloud Run URL, and keep polling as a fallback.

#### Scenario: Stage 1 polling
- **WHEN** the app runs with `VITE_LIVE=poll`
- **THEN** it refreshes data every 5 seconds and opens no `/stream` connection
