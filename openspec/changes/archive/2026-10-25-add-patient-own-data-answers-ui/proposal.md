## Why
Patients can now read server-rendered answers about their own record (`GET /portal/answers`). The patient app needs a calm place to show them.

## What Changes
- New "About my record" section on the patient Home screen: question chips, one answer open at a time, "Updated today" text, a distinct advice note with an "Ask my care team" button that scrolls to the existing ask box (`#ask-box`).
- API call + mapping + types; mock mode shows five sample cards plus advice.
- EN+TE labels in `i18nExtra.ts` (Telugu flagged for native review).

## Out of scope
Backend, `cm/`, Dockerfile, infra. Answer text is never rewritten or translated in the browser.

## Owning lane
H1/H2 web (patient app), `web/src/pages/PatientApp/`, `web/src/api/`, `web/src/mocks/`. No `cm/contracts/` change.
