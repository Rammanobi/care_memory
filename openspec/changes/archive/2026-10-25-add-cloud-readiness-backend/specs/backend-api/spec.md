## ADDED Requirements

### Requirement: Authenticated responses are not cacheable
The API SHALL send `Cache-Control: private, no-store` on responses to authenticated requests.

#### Scenario: Bearer request
- **WHEN** a request carries an Authorization header
- **THEN** the response has `Cache-Control: private, no-store`

#### Scenario: Anonymous request
- **WHEN** a request has neither Authorization nor cm_session
- **THEN** the middleware adds no Cache-Control header
