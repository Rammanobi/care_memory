# demo-accounts Specification

## Purpose
TBD - created by archiving change add-demo-accounts-3-30-60. Update Purpose after archive.

## Requirements

### Requirement: Demo accounts seed is additive and idempotent
`cm.jobs.seed_demo_accounts` SHALL create patients PT-0906 and PT-0960 with 6 and 60 days of deterministic mock history, never delete or modify existing patient or event rows, and make a second run a no-op.

#### Scenario: Second run changes nothing
- **WHEN** the job runs twice on the same database
- **THEN** the second run creates zero events and zero users

#### Scenario: History spans match
- **WHEN** the job has run
- **THEN** each patient's treatment start is 6 or 60 days before the sim date and no event is after the sim as_of

### Requirement: Safety and credentials
The job SHALL refuse unless `CM_DATA_CLASS=mock`, SHALL never print passwords, and SHALL store generated passwords only in `out/demo_accounts_credentials.txt`.

#### Scenario: Refused on real data class
- **WHEN** `CM_DATA_CLASS` is not `mock`
- **THEN** the job raises an error and writes nothing

### Requirement: Portable export and import
The job SHALL export the demo patients to a JSON bundle without passwords and import it idempotently on another database.

#### Scenario: Round trip
- **WHEN** an export is imported on the same database
- **THEN** zero new events are created

### Requirement: Earlier demo extras are retired
By default the job SHALL disable the logins of demo.pt0903, demo.pt0930 and demo.sup0930 (login returns 401, existing sessions are invalidated) without deleting any data, and SHALL be idempotent.

#### Scenario: Retired login refused
- **WHEN** the job ran with the default options on a database that had the retired accounts
- **THEN** logging in as a retired user returns 401 and the two current accounts still log in
