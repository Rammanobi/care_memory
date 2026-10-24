## ADDED Requirements

### Requirement: 60-day simulation
The simulator SHALL generate a reproducible 60-day patient course using the simulated clock and report evaluation metrics.

#### Scenario: Seeded run is reproducible
- **WHEN** the simulator runs twice with the same seed
- **THEN** metrics are identical
