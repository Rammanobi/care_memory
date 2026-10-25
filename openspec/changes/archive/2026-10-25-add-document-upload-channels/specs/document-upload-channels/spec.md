## ADDED Requirements

### Requirement: A bound patient can send a photo or document on Telegram
A message with a photo (largest size) or a document from a bound, active, consented patient chat SHALL be downloaded
through the Telegram client (getFile, then the file URL, retried through `cm.core.retry`) and passed to
`accept_upload` with source `telegram` and origin `telegram_file_unique_id`, `telegram_chat_id`,
`telegram_message_id`. A declared size over 10 MB SHALL be refused before any download, and the byte stream SHALL be
cut off at 10 MB. After a successful non-duplicate accept the task `docx-<document_id>` (kind `document_extract`)
SHALL be enqueued on `agent-runs`.

#### Scenario: Photo accepted
- **WHEN** a bound patient sends a photo with several sizes
- **THEN** the largest size is downloaded, `accept_upload` is called once, extraction is enqueued and the patient gets
  the `upload_ack_v1` template

#### Scenario: Oversize or wrong type
- **WHEN** the declared size is over 10 MB, or the intake reports `bad_type` or `too_large`
- **THEN** nothing is stored (nothing is downloaded for a declared oversize) and the patient gets `upload_rejected_v1`

#### Scenario: Unbound chat or after /stop
- **WHEN** the chat is unbound, or the patient has sent /stop
- **THEN** nothing is downloaded or stored and the existing unbound or stopped reply is sent

#### Scenario: Duplicate update
- **WHEN** the same update arrives twice
- **THEN** one document is stored, one extraction task is enqueued and the repeat is answered with nothing

### Requirement: One inline reply per upload update, caption routed once
An upload update SHALL receive at most one inline reply, acknowledgements being rate limited to one per patient per
10 minutes (shared with free text). A photo or document caption SHALL also go once through the free-text path
(doctor request, danger fast path). Reply priority: urgent caption ack, rejection, caption ack, upload ack.

#### Scenario: Danger caption
- **WHEN** a photo caption contains a danger word
- **THEN** the Red fast-path draft is raised once and the urgent acknowledgement is the only reply

### Requirement: The bot token never leaves the client
The bot token SHALL NOT appear in logs, audit rows, exceptions, replies, task payloads or stored upload data.
File fetch failures SHALL surface as `TgFileError` with a message free of the URL.

#### Scenario: Failed download
- **WHEN** the file download fails with 5xx after retries
- **THEN** the patient gets `upload_rejected_v1`, nothing is stored and no record contains the token

### Requirement: Doctor email attachments become uploads for the patient code in the message
An inbound Gmail message with attachments from a sender on `DOCTOR_EMAIL_ALLOWLIST` (and passing the same From
authentication as approve-by-reply) that carries exactly one patient code (`PT-0906`) in the subject or body SHALL
have each attachment fetched (`messages.attachments.get`) and passed to `accept_upload` with source `gmail`, origin
`gmail_message_id` and `gmail_attachment_id`, uploader the doctor person. Nothing SHALL be approved or sent to anyone
from this path.

#### Scenario: Allowlisted sender with a code
- **WHEN** an allowlisted doctor emails a PDF with `PT-0906` in the subject
- **THEN** the PDF is accepted for patient token `P-0906` and extraction is enqueued

#### Scenario: No code, or sender not allowlisted
- **WHEN** the message has no (or two different) patient codes, or the sender is not allowlisted or unauthenticated
- **THEN** nothing is fetched or stored and the refusal is audited without file names

#### Scenario: Replayed message
- **WHEN** the same message or attachment is processed again
- **THEN** the intake reports a duplicate and no second extraction is enqueued
