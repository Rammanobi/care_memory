## ADDED Requirements

### Requirement: Extraction produces a draft only
The system SHALL extract text and draft fields from an upload without writing events, tokenising PII, and never raising.

#### Scenario: text PDF
- **WHEN** a PDF with a text layer is extracted
- **THEN** masked text and fields are returned and no model is called

#### Scenario: scanned PDF
- **WHEN** a PDF has no text layer
- **THEN** the result has `needs_vision` true and the pages are not rendered

#### Scenario: prompt injection in text
- **WHEN** a document contains instructions
- **THEN** they stay data: the patient text is the fixed acknowledgement and nothing is sent

### Requirement: Doctor review item
The system SHALL create one `needs_human` approval with `subkind` `document_review` per document, notify the doctor, and use only an approved patient-safe acknowledgement text.

#### Scenario: idempotent task
- **WHEN** `document_extract` runs twice for one document
- **THEN** one approval, one SSE event and one doctor email result

### Requirement: Approval indexes, rejection does not
After a doctor decision through `decide.py`, approve or edit SHALL write events from the text excerpt and index chunks for that patient only; reject SHALL index nothing.

#### Scenario: approve
- **WHEN** a doctor approves
- **THEN** a LabResult, Dispense or ContextNote exists, chunks are searchable for that patient and not for another, and the state is `indexed`

#### Scenario: reject
- **WHEN** a doctor rejects
- **THEN** state is `rejected` and no events or chunks exist
