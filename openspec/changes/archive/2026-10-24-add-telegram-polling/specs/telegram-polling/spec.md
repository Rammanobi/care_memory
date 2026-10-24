## ADDED Requirements

### Requirement: Local polling reaches the same handler as the webhook
The poller SHALL pass every update to the inbound handler without a secret header and apply the returned reply via the Bot API.

#### Scenario: Update becomes an event
- **WHEN** a callback update arrives via getUpdates
- **THEN** the event row is saved and answerCallbackQuery is called

### Requirement: No replay after restart
The poller SHALL persist offset = last update_id + 1 and resume from it.

#### Scenario: Restart
- **WHEN** the poller restarts
- **THEN** getUpdates is called with the stored offset

### Requirement: Token never logged
Logs SHALL carry only update_id and type.

#### Scenario: Log capture
- **WHEN** updates and errors are processed
- **THEN** no log line contains the token or message text

### Requirement: Demo quiet-hours override
`DEMO_IGNORE_QUIET_HOURS=1` SHALL disable quiet hours only when `CM_ENV=dev`.

#### Scenario: Prod ignores flag
- **WHEN** CM_ENV is not dev
- **THEN** quiet hours still apply
