# web-live-updates Specification

## Purpose
TBD - created by archiving change add-web-live-updates-and-label. Update Purpose after archive.

## Requirements

### Requirement: Cloud polling
In cloud mode the web app SHALL poll every 5 s while the tab is visible and SHALL NOT open an SSE stream.
#### Scenario: firebase mode
- **WHEN** VITE_AUTH_MODE=firebase and the user is signed in
- **THEN** no EventSource is created and data is refetched every 5 s, paused while hidden

### Requirement: Demo label hidden in cloud
The demo label SHALL be hidden when VITE_AUTH_MODE=firebase or VITE_HIDE_DEMO_LABEL=1, except on localhost.
#### Scenario: cloud build
- **WHEN** the build sets VITE_HIDE_DEMO_LABEL=1 on a non-local host
- **THEN** no "demo" badge is rendered
