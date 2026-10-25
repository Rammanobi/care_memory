## Why
UI audits of the doctor console mock build found data and wording defects on Today, Patients, Patient, Ask, Lens, Admin and District.

## What Changes
- Symptom/root cause/fix, by area (lane H1/H2 web pages, mocks/seed.ts):
  - Seed: two document review requests (one empty-fields, low confidence); research brief for PT-0213 now cites evidence that says the same thing (new E-0447); the PT-0142 visit request has its own evidence E-0446 instead of reusing E-0420; PT-0198 quiet text says 6 days like its data.
  - Patient page: timeline and audit sorted newest first, one time format (`Day N · HH:MM`).
  - Ask (mock): free text with no keyword match abstains; chips are neutral and reset when the scope is cleared; Clear button label matches its text; [n] markers render as chips; sentences capitalised; 375px layout (input flex 1, Ask button auto width, chips wrap).
  - Today/Patients: tiles relabelled so patients and requests are not mixed; real weekday; request kind display labels; quiet days from one field.
  - Admin: next-change line depends on mode; Audit log section; chart domain from data.
  - Lens: confidence words (Seen once, Not known yet).
  - District mock fallback: under-5 privacy suppression and note.
- Out of scope: recharts defaultProps warning (needs package upgrade); DoctorShell, doctorKit, DraftCard, ReviewQueue, PatientApp, Supporter.
- Owning lane: web pages above. No cm/contracts change.

## Verification
`npm run typecheck`, `npm test` (new derive, Ask matcher and Admin tests), `npm run build`.
