# doctor-console Specification

## Purpose
TBD - created by archiving change add-doctor-screens. Update Purpose after archive.

## Requirements

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

### Requirement: Record answers show citation chips
The Ask page SHALL render each [D-xxxxxxxx] ref in an answer as a chip that opens the evidence drawer with the ref's date, kind and snippet.

#### Scenario: Cited answer
- **WHEN** the answer text contains `[D-1a2b3c4d]` and result_preview has a row with that ref
- **THEN** a chip is shown and clicking it opens the drawer with that row's date, kind and snippet

#### Scenario: Abstain answer
- **WHEN** the answer text is "Not in the record yet."
- **THEN** a calm abstain block shows with "The system only answers from cited records"

### Requirement: Patient-scoped Ask
Asking from a patient page SHALL prepend the patient code to the question and show a clearable scope pill.

#### Scenario: Scoped question
- **WHEN** the doctor asks "why?" with scope PT-0142
- **THEN** the request question is "PT-0142: why?" and the pill reads "Asking about PT-0142"
