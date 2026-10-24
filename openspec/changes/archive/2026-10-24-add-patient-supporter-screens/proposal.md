## Why
The patient and Supporter web screens were incomplete (only Home, Record, Ask, Me stubs). Patients need a full, accessible, bilingual app; Supporters need a minimal helper view.

## What Changes
- Patient: welcome and consent, home next-3 list, offline banner, record (calendar, visits and labs, documents), messages inbox, ask history chips, me (profile, reminder request, channel consent with revoke dialog, large text), help, privacy.
- Supporter view at /supporter; tap shows on patient Home as "marked by Supporter".
- Sample data in web/src/pages/PatientApp/sampleData.ts; empty states via Me demo switch.
- New patient-side store web/src/api/patientExtras.ts; extra i18n table (Telugu needs native review).

Out of scope: real backend, doctor screens. Lane: H2 patient/Supporter (web/src/pages/PatientApp, Supporter). Spec: feature_specs/03_dashboards_ux.md. No contract changes.
