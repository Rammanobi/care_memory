## 1. Mapping and logic
- [x] 1.1 `web/src/api/questions.ts`, `mapping.ts`, `types.ts` (research, origin, status, in_reply_to); tests in `questions.test.ts`
- [x] 1.2 `web/src/api/notify.ts` reducer, SSE bus in `realtime/sse.ts`; tests in `notify.test.ts`

## 2. Doctor UI
- [x] 2.1 `components/QuestionNotify.tsx`, `DoctorShell.tsx` badge and title
- [x] 2.2 `pages/ReviewQueue/QuestionCard.tsx`, `Requests.tsx`, `CareProvider.dispatchAsync`, `doctor2.css`

## 3. Patient app and mock
- [x] 3.1 `PatientApp/parts.tsx`, `Messages.tsx`, `liveView.ts`, `mockView.ts`, `i18nExtra.ts`
- [x] 3.2 `mocks/seed.ts` three sample questions; `npm run typecheck && npm test && npm run build`
