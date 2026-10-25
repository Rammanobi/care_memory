## ADDED Requirements

### Requirement: Whole-word document type guess
The upload doc-type guess SHALL match cue words as whole words (so "available", "label", "reported" and
"among" do not count), SHALL treat a bill, invoice or receipt as a chemist bill only with a medicine cue, and
SHALL recognise Telugu cue words.

#### Scenario: Electricity bill
- **WHEN** a text upload is an electricity bill with no medicine cue
- **THEN** its doc_type is `other`

### Requirement: Filename masked in the review payload
The doctor review payload SHALL carry the upload filename PII-tokenised.

#### Scenario: Phone number in a filename
- **WHEN** the filename contains a phone number
- **THEN** the review payload shows a token such as `[PHONE_1]` instead of the number
