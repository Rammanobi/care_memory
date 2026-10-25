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

### Requirement: Patient document upload
The patient app SHALL let a patient send a photo, PDF or text file (up to 10 MB) to the care team and show each file with a calm status.
#### Scenario: Too big
- **WHEN** the patient picks a file over 10 MB **THEN** nothing is sent and a plain message says it is too big.
#### Scenario: Duplicate
- **WHEN** the server answers duplicate **THEN** the card says "You already sent this one".

### Requirement: Doctor document review card
The Requests page SHALL show a document card with extracted fields and confidence, the line "Prepared automatically from the file. Check it against the original before approving.", and Approve and Reject buttons.
#### Scenario: Low confidence
- **WHEN** a field has low confidence **THEN** its row is highlighted.

### Requirement: Own-data answers
The system SHALL return code-computed answer cards about the signed-in patient's own record, rendered only from approved templates, with no model call.

#### Scenario: Enough history
- **WHEN** a patient with at least 3 check-ins calls `GET /portal/answers`
- **THEN** the cards taken_week, missed_week, streak, next_visit, last_refill and a final advice card are returned in the vault language

#### Scenario: Too little history
- **WHEN** the patient has fewer than 3 check-ins
- **THEN** a single history card says there is not enough history yet and no dose numbers are shown

#### Scenario: Access and isolation
- **WHEN** a doctor or Supporter calls the endpoint
- **THEN** the response is 403, and a patient never sees another patient's data or any banned term

#### Scenario: as_of
- **WHEN** events occur or are recorded after `clock.now()`
- **THEN** they do not affect any card
