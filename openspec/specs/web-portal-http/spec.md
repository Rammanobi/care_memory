# web-portal-http Specification

## Purpose
TBD - created by archiving change add-web-portal-http-data. Update Purpose after archive.

## Requirements

### Requirement: Patient and Supporter screens on real data
In http mode the patient and Supporter screens SHALL show data from the /portal routes and SHALL NOT show sample data.

#### Scenario: Reminder change
- **WHEN** the patient asks for a new reminder time and the doctor approves it
- **THEN** Me shows it as waiting, then shows the new time after the next refresh

#### Scenario: Consent switch
- **WHEN** the patient turns a channel off and confirms
- **THEN** the UI sends PUT /portal/consents and the state survives a reload

### Requirement: Doctor extras on real data
The doctor Ask page, Timeline tab, bulk approve and Settings SHALL use /query, /patients/{pid}/timeline, /review/bulk-decision and /admin/settings.

#### Scenario: Bulk route fails
- **WHEN** /review/bulk-decision errors or refuses an item
- **THEN** the UI posts single decisions for those items
