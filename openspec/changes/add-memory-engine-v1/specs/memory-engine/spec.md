## ADDED Requirements

### Requirement: Beliefs and risk are computed without an LLM
The engine SHALL compute beliefs, risk, trust and conflicts deterministically from events as of a given time.

#### Scenario: Deterministic recompute
- **WHEN** the engine runs twice over the same events and `as_of`
- **THEN** both runs produce identical stored numbers

### Requirement: Nightly pipeline persists one idempotent snapshot per patient and day
The pipeline SHALL compute features, weekday beliefs, risk with an interval and conflicts as of an instant, and
persist them through `cm/store` repos only. Engine conflicts (self-report vs refill, weekday pattern) carry `C:` refs.

#### Scenario: Same as_of twice
- **WHEN** the pipeline runs twice for one patient and the same `as_of`
- **THEN** the stored feature, belief, risk and conflict rows are identical

#### Scenario: No future leakage
- **WHEN** events occurring or recorded after `as_of` exist
- **THEN** the output for `as_of` is unchanged by them
