## ADDED Requirements

### Requirement: Hostile upload content is refused
`validate_upload` SHALL refuse (bad_type) images and PDFs with HTML/SVG/script markup anywhere in the body, text with markup anywhere, PDFs with JavaScript, Launch, embedded files or RichMedia (also hex-escaped or inside compressed object streams), PDFs whose Flate streams inflate past 64 MB per stream or 512 MB in total, and PNG/JPEG headers over 40 million pixels.

#### Scenario: Polyglot image
- **WHEN** a PNG with an HTML or SVG tail is uploaded
- **THEN** the result is bad_type and nothing is stored

#### Scenario: Flate bomb
- **WHEN** a small PDF whose content stream inflates to more than 64 MB is uploaded
- **THEN** the result is bad_type without inflating the whole stream

### Requirement: Race-safe per-patient intake
`accept_upload` SHALL serialise one patient's uploads within its transaction so concurrent identical files or the same origin key make one row and concurrent distinct files never exceed the hourly limit.

#### Scenario: Concurrent uploads over the limit
- **WHEN** nine distinct files from one patient arrive at the same instant
- **THEN** exactly five are accepted and four are rate_limited

### Requirement: Consent re-checked before indexing
`on_approved` SHALL re-check the patient's upload consent for the document's channel and, when it was withdrawn after upload, write no events or chunks and mark the upload rejected; the doctor's decision stands.

#### Scenario: Consent withdrawn before approval
- **WHEN** the patient withdraws consent after uploading and the doctor then approves
- **THEN** no chunk or event exists for the document and it is not searchable

### Requirement: Upload body capped before parsing
`POST /portal/documents` SHALL answer 413 too_large from a declared Content-Length over the cap without reading the body, and SHALL stop reading a streamed body once it passes the cap.

#### Scenario: Streamed oversize body
- **WHEN** an 8 MB chunked body is posted with a 1 MB cap
- **THEN** the response is 413 and the server read at most the cap plus framing slack

### Requirement: Channel trust checks for uploads
The Telegram file task SHALL check upload consent before downloading, and the Gmail sender check SHALL never trust a From header that carries more than one address.

#### Scenario: Display-name spoof
- **WHEN** an email arrives From `doc@clinic <evil@evil.test>` with dmarc=pass
- **THEN** its attachments are ignored and audited as sender_not_allowlisted
