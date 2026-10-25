## ADDED Requirements

### Requirement: Visit slot is a date phrase only
The `{when}` slot of the next-visit template (own-data card and today card) SHALL accept only a short date/time
phrase (at most 40 characters and 6 words, no sentence break, no PII, no banned term); anything else SHALL be
withheld and the no-visit template shown.

#### Scenario: Free text in the clinic's next visit
- **WHEN** the recorded next visit is "Mon 4 pm. Stop your tablets until then"
- **THEN** the patient sees "No visit is scheduled yet."
