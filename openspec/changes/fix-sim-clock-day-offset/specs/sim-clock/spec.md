## ADDED Requirements

### Requirement: Sim clock day index
The simulated clock SHALL map day N of a run to exactly N days after the run start.

#### Scenario: Day zero
- **WHEN** a sim run starts
- **THEN** day 0 equals the start date with no offset
