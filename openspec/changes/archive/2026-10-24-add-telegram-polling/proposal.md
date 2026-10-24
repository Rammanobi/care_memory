## Why
The real bot cannot be demoed from a laptop without a public URL. Telegram long polling needs none.

## What Changes
- `cm/jobs/tg_poll.py`: deleteWebhook, then getUpdates long poll, offset persisted under `out/`, replies applied through the Bot API.
- `cm/jobs/dev_telegram.py`: poller plus outbox drainer in one command.
- `cm/channels/telegram.py`: `handle_local_poll` (trusted path, not reachable from the HTTP route).
- `cm/channels/tg_http.py`: `get_updates`, `delete_webhook`, `answer_callback_query`.
- `cm/router/quiet_hours.py`: `DEMO_IGNORE_QUIET_HOURS=1` honoured only when `CM_ENV=dev`.
- `.env.example` names only; owner steps in `cm/channels/NOTES_integration.md`.

## Out of scope
Webhook route behaviour, contracts, inbound handler logic. Lane F/Integration.
