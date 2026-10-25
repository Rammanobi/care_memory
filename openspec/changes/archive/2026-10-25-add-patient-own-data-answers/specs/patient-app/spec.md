## ADDED Requirements
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
