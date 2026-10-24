## ADDED Requirements
### Requirement: Budget states
The governor SHALL report GREEN under 70% of today's spendable cap, AMBER from 70% to 90%, RED over 90% or after a billing error.
#### Scenario: Threshold
- **WHEN** spend is 90% **THEN** state is AMBER; **WHEN** over 90% **THEN** RED and template-only.

### Requirement: Never retry spend or auth errors
Retry SHALL apply only to 429, 5xx and timeouts; 402, 401, 403 and validation errors SHALL fail at once.
#### Scenario: 402
- **WHEN** a call returns 402 **THEN** it is attempted once and the governor goes RED.

### Requirement: PII and data class
Prompts SHALL pass assert_clean, and deepseek SHALL be refused when CM_DATA_CLASS=real.
#### Scenario: Raw phone
- **WHEN** a prompt has a raw phone number **THEN** no model is called.
