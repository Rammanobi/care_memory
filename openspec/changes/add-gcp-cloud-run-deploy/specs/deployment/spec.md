## ADDED Requirements

### Requirement: Cloud Run deployment
The system SHALL deploy cm-api and cm-sweeper to Cloud Run and jobs to Cloud Run Jobs with queues agent-runs, resumes and outbound.

#### Scenario: Deploy from clean checkout
- **WHEN** the deploy script runs with project env set
- **THEN** services start and health checks pass
