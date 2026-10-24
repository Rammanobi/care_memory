## Why
Doctor-UI audit of live mode (API :8080, web :5173) found: a misleading Undo toast, duplicate React keys in Admin, hard-coded mock channel status, silent fallback to sample data when a slice fails, about 132 requests per load, raw backend strings and citation tokens in the UI, repeated 401s when logged out, and small copy and touch-target errors.

## What Changes
Lane: H1/H2 web only (web/src). No cm/ or contracts change. Pure bug fixes, no intended-behaviour change (skip_specs).
- Live mode hides Undo (mock keeps it).
- Admin task rows merged by name, unique keys; channel status read from /admin/settings.channels, read-only, "not connected" when absent.
- Live mode starts from an empty state; failed slices are reported ("Could not load: ...") and console-warned, never replaced by sample data.
- Request count: drafts fetched only for Red items on load (cached), others on open; concurrent loads share one round; decisions refetch queue/messages/requests only; /auth/me de-duplicated.
- Plain language for "skipped:no_consent", channel names, [E-..] tokens rendered as evidence chips.
- No /stream, polling or repeated /auth/me while logged out.
- Settings copy 9 pm to 7 am; pills min 40px on phone.

Out of scope: server-side undo, cm/ changes.

## Verification
npm run typecheck, build, test (new unit tests in mapping.test.ts and sse.test.ts); browser check of request counts.
