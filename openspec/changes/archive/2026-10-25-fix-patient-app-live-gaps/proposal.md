## Why
In live mode (VITE_USE_MOCK=false) the patient and Supporter screens still showed values that /portal/* does not supply: a made-up "Day 60", an empty or sample-looking next visit, a placeholder clinic phone (000-000-0000), a default reminder "8:00 am" and a default Supporter relation "family" invented by the backend, the mock patient code as a fallback, the mock demo toggles (empty states, offline) read from localStorage, and the "From Supporter" label added twice. Goal: no sample or invented data in live mode.

## What Changes
Owning lane: G (cm/api portal routers and models) with H2 for web/src/pages/{PatientApp,Supporter} and the i18n strings (owner-authorised cross-lane fix). Implements the patient-app live-mode behaviour in `web-portal-http`.

Fields audited (every value the patient and Supporter screens show):

Backed by /portal/* (unchanged): name, code, clinic, treatment day, streak, today status and reason, 60-day history, record days and miss reasons, upcoming and past visits/labs, inbox, requests and replies, consents, documents, medicines, Supporter name, Supporter week, Supporter messages.

Fixed on the backend (new nullable semantics, no new routes, no contract model touched):
- `PortalMe.supporter.relation` and `SupporterView.relation` are `null` when the clinic recorded none (was invented "family").
- `PortalMe.reminder` is `null` until the doctor approves a reminder time (was invented "8:00 am").
- `/portal/record` appointment rows and `/portal/today` next_visit pass the banned-term filter (withheld, never rewritten).

Hidden or given an honest empty state in live mode:
- Treatment day: hidden when unknown (was "Day 60").
- Next visit: first upcoming visit the server listed, else "Nothing scheduled yet".
- Reminder: "No reminder time set yet" when none approved.
- Supporter relation: shown only when recorded.
- Clinic phone: no number shown (placeholder only in mock mode).
- Record calendar: "could not be loaded" empty state instead of a made-up calendar when /portal/record failed.
- History strip: "No doses recorded yet" when empty.
- Supporter screen: when the patient has not allowed sharing, no today status, week or messages are shown, only a plain note.
- Mock-only toggles (empty states, offline) ignored in live mode; mock patient code no longer a fallback.
- Supporter question text sent raw (the server adds the "From Supporter" label).
- Past requests: only the server's own list (sample list is mock-only).

Code: sample data is isolated to mock mode (`mockView.ts`, `sampleData.ts`); live view is a pure function (`liveView.ts`); shared types and date helpers in `portalTypes.ts`; dead `Upcoming` component with sample data removed.

Out of scope: doctor pages, cm/rag, cm/eval, cm/agents, cm/memory, cm/rules, tasks.py, Dockerfile. No frozen contract edited, so no RFC.

## Verification
vitest (liveView.test.ts: no sample strings, no sampleData imports in live screens), pytest tests/unit/api (test_portal_honest_fields.py), tests/integration/test_portal_live_gaps.py (banned-term scan of every /portal response for patient and Supporter), e2e and edge-case API suites, typecheck and build.
