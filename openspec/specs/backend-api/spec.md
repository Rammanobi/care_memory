# backend-api Specification

## Purpose
TBD - created by archiving change add-backend-slice-1. Update Purpose after archive.

## Requirements

### Requirement: Single doctor decision path
All doctor decisions SHALL go through `cm.review.decide.decide`, which writes the decision, the approval status, the audit entry and the outbox rows in one transaction, idempotent per approval.

#### Scenario: Approve writes an outbox row
- **WHEN** a doctor approves a pending approval that has recipients
- **THEN** a decision, an audit row and an outbox row referencing the approval and decision exist

#### Scenario: Double click
- **WHEN** the same decision is submitted twice
- **THEN** the second call returns the first result and writes nothing new

#### Scenario: Reject sends nothing
- **WHEN** a doctor rejects an approval
- **THEN** no outbox row exists for it

#### Scenario: No approval, no outbox
- **WHEN** an outbox row is inserted without an approval or an approved template
- **THEN** the database refuses it

### Requirement: Session auth
The API SHALL authenticate with `POST /auth/login` using scrypt password checks and an HS256 JWT in the HttpOnly cookie `cm_session`, with roles doctor, patient, supporter and admin.

#### Scenario: Wrong password
- **WHEN** the password is wrong
- **THEN** the response is 401 with an `api.Problem` body

### Requirement: Patient-facing text suppression
Patient and Supporter responses SHALL never contain TB, tuberculosis or drug names.

#### Scenario: Banned term
- **WHEN** an inbox message contains a banned term
- **THEN** it is withheld from the response

### Requirement: Deterministic seed
`python -m cm.jobs.seed` SHALL load the UI sample content idempotently with seed 42.

#### Scenario: Seed twice
- **WHEN** the seed runs twice
- **THEN** row counts are unchanged

### Requirement: Undo today's dose
The patient SHALL be able to undo today's dose without deleting any event row.

#### Scenario: Undo twice
- **WHEN** a patient who marked a dose calls DELETE /portal/dose twice
- **THEN** both calls return today as none and only one compensating event exists

### Requirement: Documents and medicines in plain language
GET /portal/documents and GET /portal/medicines SHALL return patient-safe items with no banned term and no drug name.

#### Scenario: Seeded patient
- **WHEN** the seeded patient lists medicines
- **THEN** each item has a plain label and no drug name

### Requirement: Live updates
GET /stream SHALL emit server-sent events for approval_created, approval_decided, request_created and message_sent, with a heartbeat comment every 15 s.

#### Scenario: New approval
- **WHEN** an approval row is inserted
- **THEN** a doctor stream receives an event of type approval_created

### Requirement: Per-item bulk results
POST /review/bulk-decision SHALL return HTTP 200 with one result per id carrying ok, error_code and message.

#### Scenario: Red item in the batch
- **WHEN** a red approval is in the batch
- **THEN** its result has ok false and error_code red_not_bulk while others succeed

### Requirement: District view and delivery status
GET /dashboard/district SHALL suppress small counts; the doctor message list SHALL carry delivery queued, sent or failed.

#### Scenario: Small cell
- **WHEN** a clinic count is between 1 and SMALL_CELL_THRESHOLD - 1
- **THEN** the count is null and flagged suppressed

### Requirement: Authenticated responses are not cacheable
The API SHALL send `Cache-Control: private, no-store` on responses to authenticated requests.

#### Scenario: Bearer request
- **WHEN** a request carries an Authorization header
- **THEN** the response has `Cache-Control: private, no-store`

#### Scenario: Anonymous request
- **WHEN** a request has neither Authorization nor cm_session
- **THEN** the middleware adds no Cache-Control header
