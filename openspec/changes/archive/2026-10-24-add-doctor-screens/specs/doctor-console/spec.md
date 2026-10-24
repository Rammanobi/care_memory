## ADDED Requirements
### Requirement: Doctor screens and evidence
The doctor console SHALL provide Today, Patient detail (Overview, Timeline, Messages, Notes, Audit trail), Ask, Memory Lens, District, Admin and Settings, and every citation chip SHALL open an evidence drawer.

#### Scenario: Open evidence
- **WHEN** the doctor clicks a chip such as E-0420
- **THEN** a drawer shows the source event, time, reporter and why it matters

### Requirement: Reversible approvals
Approve and Decline SHALL show an Undo toast for 10 seconds that restores the draft to waiting and removes the sent message.

#### Scenario: Undo an approval
- **WHEN** the doctor approves a draft and presses Undo within 10 seconds
- **THEN** the draft is waiting again and the audit trail records the undo

### Requirement: Ask answers use only mock data
Every number in an Ask answer SHALL be checked against the data and each claim SHALL carry a numbered citation.

#### Scenario: Ask a question
- **WHEN** the doctor asks "Why is PT-0087 flagged?"
- **THEN** the answer cites E- records and shows "Numbers checked against the data"
