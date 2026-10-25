## ADDED Requirements
### Requirement: Document reviews live on the Requests page
The system SHALL list `document_review` approvals in `GET /requests` and the doctor patient detail, with a `document`
object, and SHALL NOT list them in `/review/queue` or its counts, while counting them as pending requests.

#### Scenario: Doctor sees a document request
- **WHEN** a `document_review` approval is pending
- **THEN** `GET /requests` returns it with `kind` "document" and `document.extraction.fields`, and `/review/queue` omits it

#### Scenario: Portal never exposes it
- **WHEN** the patient calls any `/portal/*` route
- **THEN** no document_review payload, extraction field or excerpt appears
