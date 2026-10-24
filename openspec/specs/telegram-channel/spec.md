# telegram-channel Specification

## Purpose
TBD - created by archiving change add-telegram-lane. Update Purpose after archive.

## Requirements

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

### Requirement: Free text is routed to the doctor and acknowledged by template only
A message from an active, consented patient chat SHALL be stored as an event and a doctor-visible request, and answered with at most one approved template acknowledgement per person per 10 minutes. The system SHALL NOT answer its content.

#### Scenario: Normal message
- **WHEN** a bound patient sends "I travel on Friday"
- **THEN** a green request and a ContextNote event exist and the reply is the template ack without the patient's words

#### Scenario: Danger or medicine question
- **WHEN** the text has a danger word (EN or TE) or asks whether to stop or skip medicine
- **THEN** a Red (danger, plus the fast-path draft) or Amber (advice) high-priority request is created and no advice is given

#### Scenario: Repeats, unbound and stopped chats
- **WHEN** the same update id or the same words arrive again, the chat is unbound, or the patient sent /stop
- **THEN** no second request is made; unbound chats get the invitation text; after /stop nothing is stored or acked
