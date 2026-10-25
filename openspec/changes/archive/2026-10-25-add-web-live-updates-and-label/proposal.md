## Why
Doctor Requests and Approvals only refreshed on F5 in cloud mode: SSE cannot carry Bearer tokens, and the word "demo" showed in cloud builds.

## What Changes
- Cloud mode (VITE_AUTH_MODE=firebase): never open /stream; poll every 5 s, paused while the tab is hidden, immediate catch-up when it becomes visible.
- CareProvider keeps the previous state object when a poll returns identical data (no flicker, no re-render).
- "demo" live-dot and MOCK badge hidden when VITE_AUTH_MODE=firebase or VITE_HIDE_DEMO_LABEL=1; always shown on localhost.

Out of scope: backend, docs. Owning lane: H1 (web shell). Contracts untouched.
