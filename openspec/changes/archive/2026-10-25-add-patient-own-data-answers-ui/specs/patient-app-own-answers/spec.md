## ADDED Requirements
### Requirement: About my record section
The patient Home screen SHALL show tappable question chips from `GET /portal/answers`, ordered by topic, with one answer open at a time, rendering `answer_text` as sent.

#### Scenario: Open an answer
- **WHEN** the patient taps a question chip
- **THEN** its answer and an "Updated today" style line appear below it and any other open answer closes

#### Scenario: Not enough history
- **WHEN** the server sends a `history` card instead of the dose cards
- **THEN** only the history card is shown for those questions

#### Scenario: Advice footer
- **WHEN** the server sends an `advice` card
- **THEN** it is shown as a note (not a chip) with an "Ask my care team" button that scrolls to the existing ask box

#### Scenario: Load failure
- **WHEN** the request fails
- **THEN** the section shows "Could not load your record summary. Try again." with a retry button
