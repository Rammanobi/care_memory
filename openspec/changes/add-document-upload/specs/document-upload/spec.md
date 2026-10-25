## ADDED Requirements

### Requirement: Uploads require consent
`accept_upload` SHALL store nothing (no file, no row) when the patient has no granted consent for the upload source.

#### Scenario: No consent
- **WHEN** a patient without a granted consent sends a PDF
- **THEN** the result is `status=refused`, `reason=no_consent`, and neither a file nor a `cm.documents` row exists

### Requirement: Uploads are validated by content
The system SHALL accept only jpg, png, pdf and txt identified by magic bytes, at most 10 MB, at most 10 PDF pages,
and at most 5 uploads per patient per hour.

#### Scenario: Disguised file
- **WHEN** a file named `report.pdf` contains zip bytes
- **THEN** it is refused with `reason=bad_type`

#### Scenario: Rate limit
- **WHEN** a patient sends a sixth upload within one hour
- **THEN** it is refused with `reason=rate_limited`

### Requirement: Uploads are deduplicated and idempotent
The system SHALL return the existing document with `duplicate=true` for the same patient and bytes, or the same
Telegram `file_unique_id`, or the same Gmail message id and attachment id.

#### Scenario: Webhook redelivery
- **WHEN** the same Telegram update is processed twice
- **THEN** one file and one `cm.documents` row exist

### Requirement: Originals are stored outside Postgres
The original file SHALL be written through a `StoragePort` (local `data/uploads/<token>/<sha256>` now), with the pointer
on the `cm.documents` row and the lifecycle in `extra.lifecycle`.

#### Scenario: Local storage
- **WHEN** an upload is accepted
- **THEN** the file exists at `data/uploads/<token>/<sha256>` and the row's `extra.storage_uri` points to it

### Requirement: Extraction is a draft reviewed by a doctor
Extraction SHALL tokenise PII before any model call and SHALL create an approvals row with `kind=needs_human` and
`payload.subkind=document_review`; no clinical event is written before a doctor approves.

#### Scenario: Draft only
- **WHEN** a lab slip image is extracted
- **THEN** an approvals row with `data.document.extraction.fields` exists and no LabResult event exists

#### Scenario: Real data refused
- **WHEN** an image is uploaded with `CM_DATA_CLASS=real`
- **THEN** no model is called, the lifecycle is `failed`, and the review item still reaches the doctor

### Requirement: Approval writes events and indexes chunks
On approval the system SHALL write events through the existing repos with idempotency keys and index document chunks
(400 tokens, 60 overlap, parents up to 1,500) with patient_token, consent_id and sensitivity; on rejection it SHALL
mark the document withdrawn and write nothing.

#### Scenario: Approve lab report
- **WHEN** the doctor approves a lab report with two values
- **THEN** two LabResult events exist, chunks exist for the document, and the lifecycle is `indexed`

#### Scenario: Reject
- **WHEN** the doctor rejects a document
- **THEN** its status is `withdrawn` and no events or chunks exist for it

### Requirement: Patient replies use approved templates only
Patient-facing replies to an upload SHALL be the `document_ack_v1` or `document_refused_v1` templates and SHALL never
echo filenames, extracted values, drug names or TB terms.

#### Scenario: Telegram acknowledgement
- **WHEN** a patient sends a photo on Telegram
- **THEN** the reply is "We received your document. Your care team will review it." in the patient's language

### Requirement: Doctor is notified of new documents
A new document review item SHALL publish an SSE `review` event of kind `document` and call the doctor email notifier
(dry-run or send) without document contents.

#### Scenario: Notification
- **WHEN** a review item is created
- **THEN** one SSE event and at most one doctor email (deduplicated by approval_id) are produced
