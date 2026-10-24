## ADDED Requirements

### Requirement: Reminders use the patient name
The reminder job SHALL greet the patient by decrypted display name and SHALL fall back to a neutral greeting only when no name exists.

#### Scenario: Named greeting
- **WHEN** a patient with a stored name gets a reminder
- **THEN** the message greets them by that name, not "friend"
