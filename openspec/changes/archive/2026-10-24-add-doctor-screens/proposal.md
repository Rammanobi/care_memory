## Why
The doctor console only had Patients, Approvals and Requests. Judges and doctors need the rest of the console in the mock build: Today, full patient page, evidence drawer, Ask, Memory Lens, District, Admin (usage caps), Settings, with realistic sample data.

## What Changes
- New routes under /doctor: today, patients/:id (tabs), ask, lens, district, admin, settings, more.
- Evidence drawer for E-/B-/C-/R- chips, undo toast (10 s), SLA countdown and sort on Approvals, keyboard shortcuts, phone-style message preview, Sent/Seen status.
- Mock state extended to about 20 patients, 60+ events, 10 requests, messages, audit, notes, 3 clinics, 14 days of usage; empty-state flag (?empty) and Admin button.
- Removed unused scaffold files (App.tsx, index.css, doctor/, admin/, demo/, district/, Soon.tsx).

Out of scope: real backend adapter, patient and Supporter screens (other agent). Owning lane: H1 (doctor console) with H2 pages (Admin, District, Ask, Lens) built together in the mock. Implements feature_specs/03_dashboards_ux.md doctor screens. No change to cm/contracts/.
