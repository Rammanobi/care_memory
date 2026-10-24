## ADDED Requirements

### Requirement: Real Gmail adapter
The system SHALL read and send mail through a Gmail adapter using credentials from env or Secret Manager only, with every call wrapped by `cm.core.retry`.

#### Scenario: Doctor reply decides approval
- **WHEN** a doctor replies to an approval email
- **THEN** the decision is applied through `cm/review/decide.py`

### Requirement: Push authenticity
The system SHALL accept a Gmail Pub/Sub push only when its Google-signed OIDC JWT has the configured audience, issuer and service-account email.

#### Scenario: Forged push refused
- **WHEN** the JWT has a wrong audience, wrong email or bad signature
- **THEN** verification raises PushAuthError and nothing is enqueued

### Requirement: Lazy credentials
Adapters SHALL import and construct without credentials and read them only from env names on first use.

#### Scenario: Import without env
- **WHEN** no Google env names are set
- **THEN** importing and constructing the adapters succeeds and first use raises a config error naming the variable
