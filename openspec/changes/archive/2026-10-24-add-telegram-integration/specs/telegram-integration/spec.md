## ADDED Requirements
### Requirement: Telegram webhook saves events and replies inline
The API SHALL expose POST /webhooks/telegram, verify X-Telegram-Bot-Api-Secret-Token, save the event with its consent id, and return the Bot API reply as the JSON body.

#### Scenario: Bad secret
- **WHEN** the header is wrong or missing
- **THEN** the response is 401 and nothing is saved

#### Scenario: Repeated update id
- **WHEN** the same update_id arrives twice
- **THEN** exactly one event row exists

### Requirement: Outbox drainer sends only authorised rows once
The drainer SHALL claim pending rows with SKIP LOCKED, send via the sender checks, and reschedule, fail or mark sent.

#### Scenario: Revoked consent
- **WHEN** the patient sent /stop before the drain
- **THEN** the row is not sent and is marked failed with skipped:no_consent

### Requirement: Fast path Red draft
A missed-dose tap that makes 3 missed days within 3 days, or a danger symptom, SHALL create one Red approval draft per rule per day.

#### Scenario: Third missed day
- **WHEN** the patient taps Missed with two earlier missed days
- **THEN** a pending red approval exists with a template message
