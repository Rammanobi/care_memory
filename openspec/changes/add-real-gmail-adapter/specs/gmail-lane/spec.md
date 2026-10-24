## ADDED Requirements

### Requirement: Real Gmail adapter
The system SHALL read and send mail through a Gmail adapter using credentials from env or Secret Manager only, with every call wrapped by `cm.core.retry`.

#### Scenario: Doctor reply decides approval
- **WHEN** a doctor replies to an approval email
- **THEN** the decision is applied through `cm/review/decide.py`
