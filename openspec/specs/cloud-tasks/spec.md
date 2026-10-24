# cloud-tasks Specification

## Purpose
TBD - created by archiving change add-cloud-tasks-mode. Update Purpose after archive.

## Requirements

### Requirement: Cloud Tasks enqueue
In cloud mode the system SHALL create one HTTP Cloud Task per enqueue, named by the colon-free task_id, targeting `CM_TASKS_BASE_URL/tasks/run` with an OIDC token for `CM_TASKS_SA`.

#### Scenario: Create task
- **WHEN** enqueue is called with queue agent-runs, task_id and payload
- **THEN** the client receives a task whose name ends with the task_id, with the OIDC service account and audience set

#### Scenario: Duplicate name
- **WHEN** Cloud Tasks answers ALREADY_EXISTS
- **THEN** enqueue returns normally

#### Scenario: Not configured
- **WHEN** CM_TASKS_BASE_URL or CM_TASKS_SA is missing in cloud mode
- **THEN** enqueue raises a configuration error

### Requirement: Authenticated task routes
In cloud mode `/tasks/*` SHALL accept only a valid Google OIDC JWT with the configured audience and service account and SHALL fail closed otherwise.

#### Scenario: Bad token
- **WHEN** the token is missing, expired, for another audience or another email
- **THEN** the route answers 401 and runs nothing

#### Scenario: Replay
- **WHEN** a task_id that already succeeded is delivered again
- **THEN** the route answers 200 duplicate and does not run the handler

#### Scenario: Local mode
- **WHEN** TASKS_MODE=local
- **THEN** the routes still require an admin login
