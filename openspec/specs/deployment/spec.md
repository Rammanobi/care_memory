# deployment Specification

## Purpose
TBD - created by archiving change add-production-image. Update Purpose after archive.

## Requirements

### Requirement: Single production image serves API and web app
The image SHALL serve the FastAPI API and the built web app from one process, using a same-origin API base so it works on any hostname, run as a non-root user, read config only from env, and contain no `.env`.

#### Scenario: SPA fallback does not shadow the API
- **WHEN** a browser requests `/doctor` or `/patient/record`
- **THEN** `index.html` is returned with `Cache-Control: no-cache`
- **AND** `/healthz`, `/openapi.json` and `/auth/me` still answer from the API (`/auth/me` is 401 JSON)

#### Scenario: Hashed assets are cached
- **WHEN** `/assets/<hash>.js` is requested
- **THEN** it is served with `Cache-Control: public, max-age=31536000, immutable`

### Requirement: Host validation and cookie scope from env
The API SHALL reject requests whose Host is not in `CM_ALLOWED_HOSTS` (empty means any; probes exempt), set the session cookie domain from `CM_COOKIE_DOMAIN`, and mark it Secure when `CM_ENV=prod`.

#### Scenario: Unknown host
- **WHEN** `CM_ALLOWED_HOSTS=care.example.com` and a request has `Host: evil.test`
- **THEN** the response is 400
