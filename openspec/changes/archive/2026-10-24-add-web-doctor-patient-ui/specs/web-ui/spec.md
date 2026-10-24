## ADDED Requirements

### Requirement: Doctor and patient request loop
The web UI SHALL show a patient request created in the patient app in the doctor's Requests list, and a doctor approval SHALL show on the patient's Ask page as doctor approved.

#### Scenario: Patient sends a request
- **WHEN** the patient sends a request from the Ask page
- **THEN** it appears in the doctor Requests list as waiting

#### Scenario: Doctor approves
- **WHEN** the doctor presses Approve and send
- **THEN** the patient Ask page shows the reply with the label doctor approved

### Requirement: Mock data badge
The web UI SHALL show a MOCK DATA badge whenever the mock adapter is active.

#### Scenario: Mock flag on
- **WHEN** the mock flag is true
- **THEN** the badge is visible on doctor and patient screens

### Requirement: Responsive and accessible layout
The web UI SHALL work from 360 to 1920 px without horizontal scroll, use tap targets of at least 44 px, and pair every colour signal with a text label.

#### Scenario: Phone width
- **WHEN** the viewport is 390 px wide
- **THEN** navigation is a bottom tab bar and the patient detail opens as a full-screen sheet
