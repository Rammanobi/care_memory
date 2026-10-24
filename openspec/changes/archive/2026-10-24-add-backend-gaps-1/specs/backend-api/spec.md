## ADDED Requirements

### Requirement: Undo today's dose
The patient SHALL be able to undo today's dose without deleting any event row.

#### Scenario: Undo twice
- **WHEN** a patient who marked a dose calls DELETE /portal/dose twice
- **THEN** both calls return today as none and only one compensating event exists

### Requirement: Documents and medicines in plain language
GET /portal/documents and GET /portal/medicines SHALL return patient-safe items with no banned term and no drug name.

#### Scenario: Seeded patient
- **WHEN** the seeded patient lists medicines
- **THEN** each item has a plain label and no drug name

### Requirement: Live updates
GET /stream SHALL emit server-sent events for approval_created, approval_decided, request_created and message_sent, with a heartbeat comment every 15 s.

#### Scenario: New approval
- **WHEN** an approval row is inserted
- **THEN** a doctor stream receives an event of type approval_created

### Requirement: Per-item bulk results
POST /review/bulk-decision SHALL return HTTP 200 with one result per id carrying ok, error_code and message.

#### Scenario: Red item in the batch
- **WHEN** a red approval is in the batch
- **THEN** its result has ok false and error_code red_not_bulk while others succeed

### Requirement: District view and delivery status
GET /dashboard/district SHALL suppress small counts; the doctor message list SHALL carry delivery queued, sent or failed.

#### Scenario: Small cell
- **WHEN** a clinic count is between 1 and SMALL_CELL_THRESHOLD - 1
- **THEN** the count is null and flagged suppressed
