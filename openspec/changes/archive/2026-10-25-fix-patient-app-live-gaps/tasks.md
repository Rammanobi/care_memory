## 1. Backend
- [x] 1.1 relation and reminder nullable, no invented defaults (cm/api/portal_models.py, cm/api/routers/portal.py); test_portal_honest_fields.py
- [x] 1.2 banned-term filter on record appointments and next_visit (cm/api/routers/portal.py); test_portal_honest_fields.py, test_portal_live_gaps.py
## 2. Web
- [x] 2.1 portalTypes.ts, liveView.ts, mockView.ts, usePortal.ts split (web/src/pages/PatientApp); liveView.test.ts
- [x] 2.2 honest empty states: Home, Record, Me/Help, Supporter (index.tsx, Record.tsx, Me.tsx, Supporter/index.tsx, i18nExtra.ts)
- [x] 2.3 mock-only toggles and fallbacks (Shell.tsx, parts.tsx)
## 3. Verify
- [x] 3.1 npm run typecheck, npm test, npm run build
- [x] 3.2 pytest tests/unit/api, test_e2e_api.py, test_edge_cases_api.py, test_portal_live_gaps.py (note: edge test test_unknown_routes_and_methods_are_problem_bodies fails while web/dist exists, because the SPA catch-all answers unknown paths; pre-existing, unrelated)
