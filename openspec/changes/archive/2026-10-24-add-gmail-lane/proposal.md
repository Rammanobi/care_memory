## Why
Lane M needs the doctor email door (digest out, approve-by-reply in), calendar visit events, consent suppression and channel fallback, testable without Google access.

## What Changes
- Pub/Sub push handler, history fetch worker, reply parser and verifier, digest builder, outbox-only sender, watch renewal, calendar visit events, consent flows, degrade order.
- Protocols and fakes in cm/channels/ports_gmail.py and fakes_gmail.py.
- Out of scope: real Google client, DB-backed stores, OIDC verification, LLM fallback parser, district report, CSV by email.
- Owning lane: M. Spec: feature_specs/01_channels_intake.md F4, F5, F6, F11. No change to cm/contracts/.
