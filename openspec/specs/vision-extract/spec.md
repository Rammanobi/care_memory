# vision-extract Specification

## Purpose
TBD - created by archiving change add-deepseek-vision. Update Purpose after archive.

## Requirements

### Requirement: Vision extraction yields a doctor-review draft only
The system SHALL extract document images into a strict-schema draft with per-field confidence and SHALL NOT write events.

#### Scenario: Draft returned
- **WHEN** extract_document is called with a bill image
- **THEN** the result has status "draft", requires_doctor_review true, writes_events false

#### Scenario: Patient view hides drug names
- **WHEN** patient_view() is called on a draft containing medicines
- **THEN** no medicine name or dose appears

### Requirement: VISION role may use DeepSeek on synthetic data only
The VISION role SHALL accept deepseek models and SHALL refuse deepseek and image inputs when real data is configured.

#### Scenario: Real data class
- **WHEN** CM_DATA_CLASS=real
- **THEN** deepseek VISION is refused and any image part is refused
