# patient-app Specification

## Purpose
TBD - created by archiving change add-patient-supporter-screens. Update Purpose after archive.

## Requirements

### Requirement: Patient app screens
The patient app SHALL provide welcome, home, record, messages, ask, me, help and privacy screens in English and Telugu, showing only care-team-approved information.
#### Scenario: Reminder change is a request
- **WHEN** the patient picks a new reminder time
- **THEN** a request is sent to the doctor and the current time stays until approved

### Requirement: Supporter view
The Supporter view SHALL show today's status, allow marking a dose taken, and show only what the patient allowed.
#### Scenario: Supporter tap
- **WHEN** the Supporter taps Taken
- **THEN** patient Home shows "marked by Supporter"

### Requirement: Question status and reply
After asking, the patient SHALL see a status pill "Waiting for your doctor" and, once answered, "Your doctor replied" with the reply and an "In reply to your question" quote. Messages SHALL show replies with that quote. Research, brief and internal fields SHALL never reach patient screens, and every new label has a Telugu string marked for native review. No patient-facing string contains TB or medicine names.

#### Scenario: Answered question
- **WHEN** the portal reports status `answered`
- **THEN** the pill reads "Your doctor replied" and the reply text is shown

#### Scenario: Load failure
- **WHEN** requests failed to load
- **THEN** the screen shows a retry message, not an empty list
