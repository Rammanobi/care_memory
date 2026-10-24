## Why
The approved doctor and patient UI previews (ui_previews/doctor_responsive.html, patient_responsive.html) need to exist as real React screens so the demo loop (patient request, doctor approval, patient sees "doctor approved") can be shown before the backend is ready.

## What Changes
- Doctor portal: patients list with tiles and working filters, detail panel (full-screen sheet on phone), Approvals (Red/Amber/Green lanes, bulk approve Green), Requests.
- Patient app: Home, My record, Ask, Me; English/Telugu toggle; emergency note.
- Login stub at `/` to choose Doctor or Patient (no real auth).
- API layer `web/src/api/` (interface + mock adapter reading `web/src/mocks/`), MOCK DATA badge driven by a flag.
- Shared in-memory store (React context + localStorage) so patient requests appear for the doctor and approvals show for the patient.

## Out of scope
Real auth, real backend adapter, large mock dataset (a seed script will produce it), district/admin screens.

## Owning lane
H1 Doctor console (web shell and doctor pages) plus the patient app shell requested by the coordinator. Implements the dashboards UX spec (feature_specs/03_dashboards_ux.md) at mock level. Touches no `cm/contracts/`.
