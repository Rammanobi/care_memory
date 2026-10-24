## ADDED Requirements

### Requirement: Beliefs and risk are computed without an LLM
The engine SHALL compute beliefs, risk, trust and conflicts deterministically from events as of a given time.

#### Scenario: Deterministic recompute
- **WHEN** the engine runs twice over the same events and `as_of`
- **THEN** both runs produce identical stored numbers
