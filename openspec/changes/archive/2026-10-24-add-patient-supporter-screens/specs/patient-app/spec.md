## ADDED Requirements
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
