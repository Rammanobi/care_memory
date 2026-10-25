## ADDED Requirements
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
