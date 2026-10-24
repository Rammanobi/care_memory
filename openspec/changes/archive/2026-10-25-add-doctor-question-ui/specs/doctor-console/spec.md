## ADDED Requirements

### Requirement: Live notification of patient questions
The doctor console SHALL notify the doctor when an SSE `review` event with `kind` `patient_question` arrives: a toast with the patient code, category, urgency and an Open button, an unread count on the Requests nav item and in the browser tab title, and an optional sound that is off by default. Repeated events for the same `approval_id` SHALL NOT create a second notice. An urgent toast SHALL stay until the question is opened or answered.

#### Scenario: Duplicate event
- **WHEN** the same `approval_id` arrives twice
- **THEN** the unread count is 1

#### Scenario: Urgent persists
- **WHEN** an urgent notice is hidden by timeout or dismiss
- **THEN** it stays visible until the doctor opens it

### Requirement: Patient question cards
The Requests page SHALL show for each patient question the text, channel badge, category and urgency chips, patient code link, waiting time with SLA colours, a research panel (pending skeleton, ready brief with citation chips and "Prepared from the record. The decision is yours.", or an honest failure message), and an editable reply prefilled from `suggested_reply` with a character count, a hint for words the server blocks, and Send reply / Decline buttons. A server refusal SHALL be shown in plain words and nothing is shown as sent.

#### Scenario: Research failed
- **WHEN** `research.status` is `failed`
- **THEN** the card says so and the doctor can still reply

#### Scenario: Blocked word
- **WHEN** the server refuses the reply for a blocked word
- **THEN** the card shows a plain message and stays open
