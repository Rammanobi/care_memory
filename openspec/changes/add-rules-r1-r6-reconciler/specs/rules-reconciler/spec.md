## ADDED Requirements

### Requirement: Rules R1-R6 evaluate per patient
The system SHALL evaluate rules R1 to R6, including household contact screening, and emit findings that route only through the review gate.

#### Scenario: Rule hit becomes a draft
- **WHEN** a rule fires for a patient
- **THEN** an approval draft is created and nothing is sent
