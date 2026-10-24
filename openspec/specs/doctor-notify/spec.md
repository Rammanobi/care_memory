# doctor-notify Specification

## Purpose
TBD - created by archiving change add-doctor-email-notify. Update Purpose after archive.

## Requirements

### Requirement: Doctor email on new patient question
The system SHALL email the doctor a notification with the patient code, channel, category, urgency, a PII-masked excerpt of at most 200 characters, the time and a console link, and SHALL never include a patient name or AI-written text.
#### Scenario: Urgent question
- **WHEN** an urgent symptom question for PT-0903 arrives **THEN** the subject is "[CareMemory] Urgent patient question PT-0903 (symptom)" and phone numbers in the excerpt are masked.

### Requirement: Modes and safety
DOCTOR_NOTIFY_MODE SHALL be off, dry-run (default) or send. Dry-run SHALL write an .eml under out/email_outbox/ and never contact Gmail. Send SHALL require the Gmail env, else the call is skipped with reason "gmail not configured". The function SHALL never raise.
#### Scenario: Dry-run
- **WHEN** mode is dry-run **THEN** status is dry_run, a file path is returned and no Gmail call is made.

### Requirement: Idempotency and throttle
A second call for the same approval_id SHALL be skipped as duplicate. Normal and high priority SHALL send at most one email per patient per 10 minutes; urgent SHALL always send but at most 3 per patient per hour.
#### Scenario: Throttled
- **WHEN** two normal questions for one patient arrive 5 minutes apart **THEN** the second is skipped as throttled.

### Requirement: Guarded test email
The CLI `--send-test --to-env` SHALL send one labelled test email only when mode is send, Gmail env is configured and `--i-confirm-owner-approved` is passed; otherwise it SHALL print what it would send and exit 0.
#### Scenario: No confirmation
- **WHEN** the flag is missing **THEN** nothing is sent and exit code is 0.
