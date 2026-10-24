## ADDED Requirements

### Requirement: Approved message templates in English and Telugu
Every routine patient and Supporter message kind SHALL have an approved template in `cm/router/templates/*.yaml` with an English and a Telugu block, a telegram variant and an email variant, and declared placeholders.

#### Scenario: Template structure is complete
- **WHEN** the template files are parsed
- **THEN** each of the 12 kinds (daily_checkin_reminder, missed_dose_nudge, visit_reminder, lab_reminder, refill_reminder, reminder_time_changed, visit_moved, request_received, supporter_weekly_summary, consent_confirmation, consent_revoke_confirmation, emergency_note) appears once with `doctor_approved: true`, tier green, and both `en` and `te`

#### Scenario: Placeholders match declarations
- **WHEN** a template's English and Telugu strings are scanned for `{name}` placeholders
- **THEN** the names are exactly the declared `placeholders` list

#### Scenario: Telugu is flagged for review
- **WHEN** a Telugu block is read
- **THEN** its first line is the comment `# needs native-speaker review`

### Requirement: Fixture text bank
`fixtures/text_bank.json` SHALL hold 30 fictional patient replies and 30 fictional doctor-facing drafts for tests and the simulator.

#### Scenario: Counts and clean patient replies
- **WHEN** the text bank is loaded
- **THEN** there are 30 patient replies and 30 doctor drafts, and no patient reply contains a banned term

### Requirement: Banned-term scan for patient and Supporter text
`scripts/banned_terms.py` SHALL reject the terms TB (uppercase whole word), tuberculosis, the nine drug names, and the non-Latin and DOTS terms from architecture section 3.11, in patient and Supporter-facing sources. It SHALL exit 1 and print file and line on a hit.

#### Scenario: Bad sample is caught
- **WHEN** the text "Your TB medicine is ready." is scanned
- **THEN** a hit for TB is reported

#### Scenario: Word boundaries avoid false positives
- **WHEN** the text "TBD" or "table" is scanned
- **THEN** no hit is reported

#### Scenario: Repository is clean
- **WHEN** the scanner runs on the repository
- **THEN** it exits 0 (or the hits are reported as a failure, not hidden)
