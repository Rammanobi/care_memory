## ADDED Requirements

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
