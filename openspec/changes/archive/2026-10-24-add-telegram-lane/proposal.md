## Why
Patients and Supporters need a working Telegram path: taps become events, replies are fast, outbound messages are gated. Everything must be testable with no token and no network.

## What Changes
- Lane F: inbound webhook handler (secret check, dedupe `tg:{update_id}`, tap to dose/symptom event saved first, task `tg-{update_id}`, rules fast path), bind and stop flow, outbound sender (approved rows only, quiet hours, 1 msg/s per chat token bucket, retry-after, no auth retry, idempotent), router (channel choice, fallback), banned-term check, Supporter web helpers, fake update builders.
- Protocols in `cm/channels/ports.py`; the real store implements them (integrator wires).
- Env names only, all already in `.env.example`: TELEGRAM_BOT_TOKEN (one bot), TELEGRAM_WEBHOOK_SECRET, TELEGRAM_PER_CHAT_RPS, TELEGRAM_GLOBAL_RPS, INBOUND_PER_CHAT_PER_MIN, PUBLIC_BASE_URL. No new variables.

Out of scope: real HTTP client calls, onboarding wizard, free-text intake agent, household wizard, webpush, degrade.py (lane M), template YAML (lane K).
Owning lane: F. Spec: feature_specs/01_channels_intake.md F1, F3, F11 binding, router 3.11. No change to `cm/contracts/`.

## Impact
New code in cm/channels and cm/router only.
