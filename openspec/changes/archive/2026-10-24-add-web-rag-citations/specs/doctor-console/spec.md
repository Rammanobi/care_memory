## ADDED Requirements
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
