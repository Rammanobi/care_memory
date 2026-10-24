## ADDED Requirements

### Requirement: Question status and reply
After asking, the patient SHALL see a status pill "Waiting for your doctor" and, once answered, "Your doctor replied" with the reply and an "In reply to your question" quote. Messages SHALL show replies with that quote. Research, brief and internal fields SHALL never reach patient screens, and every new label has a Telugu string marked for native review. No patient-facing string contains TB or medicine names.

#### Scenario: Answered question
- **WHEN** the portal reports status `answered`
- **THEN** the pill reads "Your doctor replied" and the reply text is shown

#### Scenario: Load failure
- **WHEN** requests failed to load
- **THEN** the screen shows a retry message, not an empty list
