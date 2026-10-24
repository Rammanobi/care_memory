## ADDED Requirements

### Requirement: Events render to name-free factual sentences
The renderer SHALL turn each event into a short sentence using the patient token only, never embedding lab values,
raw CSV rows, names or drug names.

#### Scenario: Dispense row
- **WHEN** a Dispense event with a bill number and tablets is rendered
- **THEN** the text states a refill was recorded and contains neither bill number nor tablet count

### Requirement: Deterministic chunking strategies
`chunk_text` SHALL support `fixed`, `sentence`, `event` and `dynamic` strategies, deterministically and without an LLM.

#### Scenario: Fixed overlap
- **WHEN** text is chunked with size 256 and overlap 100 (or 200)
- **THEN** consecutive chunks share that many tokens and the same input gives identical output

### Requirement: Rollup chunks come from memory features only
Daily and weekly chunks SHALL be built from `cm.memory` features; their numbers are stored in `extra.numbers`.

#### Scenario: Weekly rollup
- **WHEN** a week has misses
- **THEN** the weekly chunk text and `extra.numbers` agree with `compute_features`

### Requirement: Idempotent, as_of-safe, PII-clean index build
`build_patient_index` SHALL write only through `chunks_repo`, never duplicate on re-run, exclude events not visible at
`as_of`, and store tokenized text that passes `assert_clean`.

#### Scenario: Re-run
- **WHEN** the build runs twice with the same arguments
- **THEN** the chunk count is unchanged

#### Scenario: Future event
- **WHEN** an event occurs after `as_of`
- **THEN** no chunk is created for it
