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
