# gmail-lane Specification

## Purpose
TBD - created by archiving change add-gmail-lane. Update Purpose after archive.

## Requirements

### Requirement: Approve-by-reply is verified and one-time
The system SHALL apply a reply only if the sender is the registered doctor with passing authentication, the thread matches the digest, and each per-item token is unused and unexpired.

#### Scenario: Spoofed or forwarded mail
- **WHEN** the sender, thread or subject check fails
- **THEN** nothing is decided and an audit event is recorded

#### Scenario: Reused token
- **WHEN** an item token was already consumed
- **THEN** the item is skipped as already applied

### Requirement: Outbound Gmail needs approval
The system SHALL send Gmail only from approved outbox rows.

#### Scenario: Missing approval reference
- **WHEN** an outbox row has no approval_ref or template_id
- **THEN** the send is refused and Gmail is not called

### Requirement: Calendar events do not leak attendees
The system SHALL add a patient attendee only when consent allows.

#### Scenario: No patient consent
- **WHEN** a visit event is created without email consent
- **THEN** no attendee is added and the event id is deterministic

### Requirement: Real Gmail adapter
The system SHALL read and send mail through a Gmail adapter using credentials from env or Secret Manager only, with every call wrapped by `cm.core.retry`.

#### Scenario: Doctor reply decides approval
- **WHEN** a doctor replies to an approval email
- **THEN** the decision is applied through `cm/review/decide.py`

### Requirement: Push authenticity
The system SHALL accept a Gmail Pub/Sub push only when its Google-signed OIDC JWT has the configured audience, issuer and service-account email.

#### Scenario: Forged push refused
- **WHEN** the JWT has a wrong audience, wrong email or bad signature
- **THEN** verification raises PushAuthError and nothing is enqueued

### Requirement: Lazy credentials
Adapters SHALL import and construct without credentials and read them only from env names on first use.

#### Scenario: Import without env
- **WHEN** no Google env names are set
- **THEN** importing and constructing the adapters succeeds and first use raises a config error naming the variable
