# rules-reconciler Specification

## Purpose
TBD - created by archiving change add-rules-r1-r6-reconciler. Update Purpose after archive.

## Requirements

### Requirement: Rules R1-R6 evaluate per patient
The system SHALL evaluate rules R1 to R6, including household contact screening, and emit findings that route only through the review gate.

#### Scenario: Rule hit becomes a draft
- **WHEN** a rule fires for a patient
- **THEN** an approval draft is created and nothing is sent

### Requirement: Deterministic, cited conflicts
`cm.rules.reconcile.reconcile_frame(events, patient, as_of, thresholds)` SHALL be a pure function that returns the same conflicts for the same events in any order, with `conflict_id = uuid5(NS, "{pid}|{rule}|{anchor}")`, and every conflict SHALL cite only `E:` refs of events of that patient visible at `as_of` (occurred and recorded on or before it). No LLM computes any number.

#### Scenario: Shuffled input
- **WHEN** the same events are passed in a different order
- **THEN** the conflicts, ids and titles are identical

#### Scenario: Late-recorded event
- **WHEN** an event occurred before `as_of` but was recorded after it
- **THEN** it is neither used nor cited

### Requirement: R1 refill gap respects chemist lag
R1 SHALL fire only when the supply ledger, counting each dispense from the day it was known, has been empty for at least 3 days and the patient self-reported "taken" on at least 3 distinct days in the gap; it SHALL close when a covering dispense is recorded.

#### Scenario: Dispense recorded two days late
- **WHEN** a refill occurred on time but was recorded 2 days later
- **THEN** R1 never fires

### Requirement: R6 contacts not screened
From treatment day `contacts_due_day` R6 SHALL raise an Amber conflict when zero household contacts are listed or any listed contact is unscreened, SHALL be suppressed by a `ContextNote{kind:"household_declined"}`, SHALL close when all listed contacts are screened, and SHALL never include contact names.

#### Scenario: Contact unscreened at due day
- **WHEN** a listed contact has no screening by day 14
- **THEN** an Amber R6 conflict opens on day 14 and closes on the day the last contact's screening is recorded

### Requirement: Fast path and drafts
`fast_path(event)` SHALL run only R2 and R4 and produce the same conflict ids as the nightly run. Conflict drafts SHALL be doctor-facing, have no channel and no recipients, be deduped on `conflict_id`, and cite the conflict (`C:`) and its evidence.

#### Scenario: Danger symptom on ingest
- **WHEN** a SymptomReport with a danger sign is appended
- **THEN** the fast path returns one Red R4 conflict and its draft has no channel or recipients
