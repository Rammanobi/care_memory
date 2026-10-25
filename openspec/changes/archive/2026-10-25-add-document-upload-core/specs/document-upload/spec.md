## ADDED Requirements

### Requirement: Safe document intake
`accept_upload` SHALL accept only jpg, png, pdf (at most 30 pages) and utf-8 txt by magic bytes up to UPLOAD_MAX_MB, require active consent, allow at most 5 uploads per patient per wall-clock hour, deduplicate by content and origin key, and return a reason code instead of raising.

#### Scenario: Accepted upload
- **WHEN** a consenting patient uploads a valid file
- **THEN** the original is stored under `<patient_token>/<sha256>` and a documents row with `upload_state` received exists

#### Scenario: Rejected upload
- **WHEN** consent is missing, the type is spoofed, the file is too large, or the sixth upload in an hour arrives
- **THEN** the result carries no_consent, bad_type, too_large or rate_limited and nothing is stored

#### Scenario: Duplicate
- **WHEN** the same bytes or the same Telegram or Gmail origin key arrive again
- **THEN** the existing document id is returned with duplicate true and no new row

### Requirement: Portal upload and listing
`POST /portal/documents` SHALL take the patient from the session only and enforce the size cap while streaming; `GET /portal/documents` SHALL show a patient-safe status and never extracted contents.

#### Scenario: Status mapping
- **WHEN** an upload is received, extracting, pending_review, accepted or failed
- **THEN** the patient sees received, received, with your care team, added to your record, could not be used
