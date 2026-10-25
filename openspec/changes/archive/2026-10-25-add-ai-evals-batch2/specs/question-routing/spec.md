## ADDED Requirements

### Requirement: Hindi danger spelling variants
Question triage SHALL treat the chandrabindu spelling of "yellow eyes" and the Hindi word for vomiting as danger
words, so such questions are `urgent` like their English and Telugu equivalents.

#### Scenario: Yellow eyes in Hindi
- **WHEN** a patient writes "मेरी आँखें पीली हो गई हैं"
- **THEN** the triage priority is `urgent` and the suggested reply carries the 108 line
