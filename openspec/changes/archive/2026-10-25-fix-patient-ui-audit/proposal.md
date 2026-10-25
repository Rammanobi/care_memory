## Why
UI audits of the patient app and Supporter view (mock build) found defects: SVG accepted by upload validation, "Done" shown after a missed dose, consent revoke with no downstream effect, doctor replies missing from Messages, Telugu gaps, contradicting sample answers, a placeholder phone number, accessibility gaps, unconfirmed Supporter dose marking.

## What Changes
Bug fixes in `web/` patient lane only (lane: web patient app + Supporter). Symptom, root cause and fix per defect:
1. Upload validation allowed any `image/*` (SVG). Now an explicit list: png, jpeg, webp, heic, heif, gif, pdf, txt.
2. Home "Next 3 things" ticked Done for a missed dose. Now shows a missed state.
3. Mock consent revoke did nothing. Telegram off changes the channel and reminder text; new mock "Share with my Supporter" switch drives Supporter `allowed`; Supporter view shows only the sharing-off note when off.
4. Replies to patient-app questions were filtered out of Messages by `r.origin`. Filter dropped (archived excluded), threaded "In reply to your question".
5. Hard-coded English in mock view/sample data, times, relative dates, demo card, document kinds, missed reasons: EN+TE added (Telugu needs native review).
6. Mock "About my record" answers are language-aware and derived from the Home sample values.
7. Help placeholder phone removed in mock.
8. Accessibility: focus management, dialog focus trap and restore, 44px back links, real tabs on Record.
9. Supporter "Taken for" has a confirm step.
10. Reminder picker disables the current time, offline banner sticky, new-request send button matches intent.

Out of scope: backend, live-mode data, doctor pages, seed.ts. No contracts touched.

## Verification
`npm run typecheck`, `npm test`, `npm run build`, new vitest cases.
