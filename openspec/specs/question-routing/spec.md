# question-routing Specification

## Purpose
TBD - created by archiving change add-doctor-question-routing. Update Purpose after archive.

## Requirements

### Requirement: Question capture and research
A patient question SHALL be stored with `data.origin` and `data.research` (status `pending`) and enqueue `question_research` idempotently per approval.

#### Scenario: Telegram question
- **WHEN** a bound patient sends free text on Telegram
- **THEN** the request holds origin chat id, message id and a banned-term-clean excerpt of at most 80 characters, and research status `pending`

#### Scenario: Task re-run
- **WHEN** the research task runs twice for one approval
- **THEN** the brief is computed once and the doctor is notified once

#### Scenario: Urgent triage
- **WHEN** triage says urgent
- **THEN** the tier is raised to red and an existing red tier is never lowered

### Requirement: Doctor notification
When the brief is stored the system SHALL publish an SSE `review` event `patient_question` with approval id, patient code, category and priority (no patient text), and call the doctor notifier without ever failing the task.

#### Scenario: Notify failure
- **WHEN** research or the notifier raises
- **THEN** the research is stored as `failed` and the task still succeeds

### Requirement: Threaded reply on the same channel
A doctor approval or edit (via `decide` only) of a question SHALL write an outbox row on the question's channel with `meta.reply_to`.

#### Scenario: Telegram reply
- **WHEN** the sender delivers the row
- **THEN** it is sent with `reply_to_message_id` and a first line quoting the question in the patient's language

#### Scenario: Cap and quiet hours
- **WHEN** the daily cap is used up
- **THEN** the reply is still sent and is not counted; during quiet hours only an urgent reply is sent

#### Scenario: Consent revoked
- **WHEN** consent is revoked before delivery
- **THEN** nothing is sent and the row fails with `skipped:no_consent`

### Requirement: Patient-safe status
`/portal/*` SHALL show per question `waiting`, `answered` (with the reply) or `closed` (declined) and SHALL NOT expose research, brief, suggested reply or origin.

#### Scenario: Web reply
- **WHEN** the doctor answers a portal question
- **THEN** `/portal/inbox` shows the reply with `in_reply_to` and `/portal/requests` shows `answered`

### Requirement: Hindi danger spelling variants
Question triage SHALL treat the chandrabindu spelling of "yellow eyes" and the Hindi word for vomiting as danger
words, so such questions are `urgent` like their English and Telugu equivalents.

#### Scenario: Yellow eyes in Hindi
- **WHEN** a patient writes "मेरी आँखें पीली हो गई हैं"
- **THEN** the triage priority is `urgent` and the suggested reply carries the 108 line
