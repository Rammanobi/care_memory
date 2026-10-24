# ai-runtime Specification

## Purpose
TBD - created by archiving change add-ai-runtime. Update Purpose after archive.

## Requirements

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

### Requirement: Patient questions are triaged deterministically
The system SHALL classify a patient's free-text question into a category (medicine, food, symptom, visit,
admin, other) and a priority (normal, high, urgent) without an LLM, in English, Telugu and Hindi. Danger
words SHALL give priority urgent. Medicine, food and symptom questions SHALL always need the doctor.

#### Scenario: food question
- **WHEN** the patient asks "Can I eat chicken?"
- **THEN** the category is food, the priority is high and needs_doctor is true

#### Scenario: danger words
- **WHEN** the patient writes "I am vomiting blood" or "రక్తం వాంతి"
- **THEN** the priority is urgent

### Requirement: Doctor-facing research brief, never a patient answer
For a patient question the system SHALL prepare a doctor-facing brief of 3 to 6 sentences and a suggested
patient reply for the doctor to edit and approve; it SHALL NOT send anything to the patient. Every brief
fact sentence SHALL cite record refs and pass cite-or-cut, the content guard and the doctor banned
lexicon, or be dropped. The brief SHALL state what the record does not show and that clinical judgment is
the doctor's. A patient with little history SHALL get a brief that says so, with confidence low.

#### Scenario: ungrounded sentence is cut
- **WHEN** the model writes a sentence without a ref or with a number not in the cited evidence
- **THEN** that sentence is not in the brief

#### Scenario: day-3 patient
- **WHEN** the patient has fewer than 7 dose check-ins
- **THEN** the brief says the record has little history and confidence is low

### Requirement: Suggested reply is validated deterministically
The suggested reply SHALL be 1 to 3 short sentences in the patient's language (vault language, Telugu
script in the question wins), free of banned terms, drug names, doses and advice, and SHALL defer to the
doctor. Any model-proposed wording that fails the validator SHALL be replaced by the fixed holding reply;
urgent questions SHALL include the 108 line.

#### Scenario: dosing request
- **WHEN** the patient asks "Can I take two tablets of rifampicin tonight?"
- **THEN** the suggested reply contains no drug name, no number and no instruction to take or stop anything

### Requirement: Research degrades and never raises
Without a model key or with a RED budget the system SHALL produce an extractive brief from retrieved
chunks and computed features. Any failure SHALL return status failed with a reason instead of raising.

#### Scenario: unknown patient
- **WHEN** research runs for a token that does not exist
- **THEN** the result has status failed and a reason
