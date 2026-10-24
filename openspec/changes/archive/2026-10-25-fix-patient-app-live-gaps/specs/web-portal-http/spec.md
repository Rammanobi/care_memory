## ADDED Requirements

### Requirement: Live patient and Supporter screens show only server-backed data
In live mode the patient and Supporter screens SHALL show only values returned by /portal/*. A value the server did not send SHALL be hidden or shown as an honest empty state, never replaced by sample or invented data.

#### Scenario: nothing scheduled
- **WHEN** the server sends no next visit and no upcoming visit
- **THEN** the Home screen shows "Nothing scheduled yet"

#### Scenario: unknown treatment day
- **WHEN** the treatment day is not known
- **THEN** no "Day N" line is shown

#### Scenario: no recorded Supporter relation or reminder
- **WHEN** /portal/me returns relation null and reminder null
- **THEN** the profile shows the Supporter name only and the reminder card says no reminder time is set

#### Scenario: sharing not allowed
- **WHEN** the Supporter view has allowed false
- **THEN** no dose status, week strip or messages are shown, only a note that sharing is not allowed yet

### Requirement: Portal text fields are never invented and always filtered
/portal/me and /portal/supporter/checkin SHALL return null for a relation or reminder the clinic has not recorded, and every text field in every /portal response SHALL be free of banned terms.

#### Scenario: banned term in a stored appointment
- **WHEN** a stored appointment note contains a banned term
- **THEN** that appointment is withheld from /portal/record
