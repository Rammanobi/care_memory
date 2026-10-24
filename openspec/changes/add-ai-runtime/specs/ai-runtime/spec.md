## ADDED Requirements

### Requirement: Numbers come only from feature helpers
Stored and cited numbers SHALL be computed by `cm.memory.features`, never by an LLM.

#### Scenario: Wrong number is cut
- **WHEN** a narrated sentence states a number that is not in the features
- **THEN** cite-or-cut removes that sentence

### Requirement: Cite or cut
Every sentence of a doctor-facing card SHALL carry a citation that resolves to a real event or feature id, or it is cut; if all are cut a template card is used.

#### Scenario: Uncited sentence
- **WHEN** a sentence has no valid citation
- **THEN** it is removed from the card

### Requirement: Nothing is sent without the doctor
The orchestrator SHALL pause at submit_for_review and create a pending approval; no outbox row exists until a doctor decides.

#### Scenario: Interrupt then resume
- **WHEN** the orchestrator reaches submit_for_review
- **THEN** the run is interrupted and, after approval, an approval row exists in status pending

### Requirement: Governed model use
Every model call SHALL go through `cm.core.llm.get_model`; RED budget SHALL yield the template card.

#### Scenario: RED
- **WHEN** the governor is RED
- **THEN** the narrator returns the template card and no model is called
