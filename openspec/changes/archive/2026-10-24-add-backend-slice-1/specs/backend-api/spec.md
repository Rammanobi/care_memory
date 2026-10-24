## ADDED Requirements

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
