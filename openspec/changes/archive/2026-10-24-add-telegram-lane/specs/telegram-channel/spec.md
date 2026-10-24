## ADDED Requirements

### Requirement: Webhook verification and dedupe
The webhook SHALL reject a wrong or missing secret header with 401 and SHALL process each `update_id` once.

#### Scenario: Wrong secret
- **WHEN** the header does not match
- **THEN** the result is 401 and nothing is stored

#### Scenario: Repeat update
- **WHEN** the same update_id arrives twice
- **THEN** one event exists and the second reply is still ok

### Requirement: Tap becomes event before reply
A callback tap from a bound, consented chat SHALL be saved as a dose or symptom event before the reply is built, and a task `tg-{update_id}` SHALL be enqueued.

#### Scenario: Missed tap
- **WHEN** a bound patient taps Missed
- **THEN** a DoseCheckin missed event is saved and the missed-dose fast path is called

#### Scenario: No consent
- **WHEN** the bound person has no active consent
- **THEN** no event is stored

### Requirement: Gated outbound
The sender SHALL refuse a row with no approval_ref or template, SHALL refuse banned terms, SHALL respect quiet hours, a 1 msg/s per chat limit and retry-after, and SHALL never retry auth errors.

#### Scenario: No approval
- **WHEN** a row has neither approval_id nor template_id
- **THEN** it is failed with skip reason invalid_approval and nothing is sent

#### Scenario: Banned word to Supporter
- **WHEN** the text contains TB, tuberculosis or a drug name
- **THEN** it is blocked with skip reason banned_term
