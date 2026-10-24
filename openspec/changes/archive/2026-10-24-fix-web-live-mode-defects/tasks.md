## 1. Fixes
- [x] 1.1 Undo hidden in live mode (web/src/components/doctorKit.tsx)
- [x] 1.2 Admin keys, merged tasks, real channels (pages/Admin, api/mapping.ts mergeTasks/mapChannels)
- [x] 1.3 Live empty state and loadErrors (api/httpAdapter.ts, CareProvider.tsx)
- [x] 1.4 Lazy drafts, shared loads, targeted refetch (api/httpAdapter.ts, DraftCard, ReviewQueue)
- [x] 1.5 Friendly strings and citation chips (api/mapping.ts, DraftCard, PatientPage)
- [x] 1.6 Logged-out 401s (api/http.ts getMe, auth/session.tsx, realtime/sse.ts)
- [x] 1.7 Settings copy and touch targets (Settings, styles/doctor.css)
## 2. Verify
- [x] 2.1 typecheck, build, test (mapping.test.ts, sse.test.ts)
