# Lane F notes (Telegram, Supporter, router)

Verified: `pytest tests/unit/channels` (23 passed). No network, no token.

## Integrator wiring (Protocols in `cm/channels/ports.py`)
| Protocol | Real implementation |
|---|---|
| `BindingPort` (by_chat, by_invite, by_person, activate, set_status) | adapter over `channel_bindings` (lane A store) |
| `EventPort.append_event(dict)` | `cm.store.events_repo.append_event(NewEvent(**d))`, returns `(event_id, inserted)` |
| `ConsentPort` (has_consent, record_consent) | `cm.store.consent.has_consent` / `record_consent` |
| `OutboxPort` (get, mark, already_sent, sent_today) | `cm.store.outbox_repo` (needs get, mark, dedup lookup, daily count) |
| `TaskPort.enqueue(queue, name, payload)` | `cm.core.tasks.enqueue` (same signature) |
| `FastPathPort` (missed_dose, red_symptom) | rules/gate hand-off (lane E/D) |
| `AuditPort`, `TelegramClient` | audit_log writer; httpx Bot API client (raises TgRetryAfter/TgAuthError/TgBlocked/TgTransient) |

Route: `POST /webhooks/telegram` calls `cm.channels.telegram.handle_webhook(body, header X-Telegram-Bot-Api-Secret-Token, deps)` -> `(status, json)`. Return the JSON body inline.
Drainer: call `tg_sender.send_outbox(row, SenderDeps(...))` per claimed row; act on `SendResult` (`retry` -> reschedule using `retry_after_s`).

## Env names (all already in .env.example)
TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, TELEGRAM_PER_CHAT_RPS, TELEGRAM_GLOBAL_RPS, INBOUND_PER_CHAT_PER_MIN, PUBLIC_BASE_URL.

## Not done / open
- Real httpx client, setWebhook script, onboarding wizard (itemised consent), language/time commands, weight/payment replies, free-text intake beyond enqueueing `tg-{update_id}`, household wizard, webpush, factory.
- `/start <code>` grants telegram daily_checkin and care_coordination consent directly (placeholder for itemised onboarding).
- Inbound flood limit (INBOUND_PER_CHAT_PER_MIN) not enforced yet; the 2-hour answer lock and `supersedes` on changed answers not implemented (late flag only).
- Supporter proxy taps (`px:`, `v:`) not handled in the webhook; helpers only in `supporter_web.py`.
- Global rate limit is per process; the spec asks for a Postgres advisory lock per chat in the drainer.
