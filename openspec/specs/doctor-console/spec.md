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
