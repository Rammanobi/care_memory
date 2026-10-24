# Telegram integration: owner steps

No secret is stored in code or logs. You put the two values in `caremem/.env` yourself.

1. Edit `caremem/.env` (git-ignored). Set `TELEGRAM_BOT_TOKEN` (from BotFather) and `TELEGRAM_WEBHOOK_SECRET`
   (any random 32 characters). Keep `TASKS_MODE=local`. Make sure Postgres is up (`docker compose up -d db`) and migrated/seeded.
2. Start the API: `uvicorn cm.api.main:app --port 8080`. In local mode it also starts the in-process task worker.
3. Start ngrok: `ngrok http 8080`. Copy the https URL.
4. Put it in `.env` as `PUBLIC_BASE_URL=https://xxxx.ngrok-free.app`, then restart the API (or just run step 5, which re-reads `.env`).
5. Register the webhook: `python scripts/tg_set_webhook.py` (prints OK or FAILED only). Remove with `--delete`.
6. Make a one-time code for the demo patient: `python -m cm.jobs.make_invite --patient PT-0142` (also accepts `P-0142`). Prints the code and the line to send.
7. In Telegram open your bot and send `/start CODE`. The bot replies "You are connected."
8. Create today's check-in: `python -m cm.jobs.reminders --now`, then send it: `python -m cm.jobs.outbox_drainer --once`
   (or leave `python -m cm.jobs.outbox_drainer` running; it polls every 5 s). Tap Taken / Missed / Feeling unwell.
   Taps are saved as events. A third missed day in 3 days, or a danger symptom, creates a Red draft in the doctor queue
   (web console). When the doctor approves it, the next drainer run sends it to you.
9. `/stop` in the chat withdraws consent and revokes the binding; later sends are skipped.

Notes
- Quiet hours (21:00 to 07:00 IST) defer reminders and approved messages (not red alerts). Replies to your own messages are inline and not affected. If you test at night, nothing is sent until morning.
- The sim clock: if the DB has an active sim clock the API pins "now" to it; reminders and quiet hours follow that clock.
- Per chat limit is 1 message/second and max 3 messages per person per IST day (existing sender rules).

## What exists
`adapters_pg.py` (Postgres adapters + FastPathPort), `tg_http.py` (httpx client, token read at call time, errors rewrapped),
`POST /webhooks/telegram`, `cm/jobs/{outbox_drainer,reminders,make_invite,tg_set_webhook}.py`, `cm/core/tasks.py` local queue,
`cm/core/budget_pg.py` (DB UsageStore, installed at API startup), `GET /admin/usage/caps` (budget numbers),
`cm/store/channels_repo.py` (SQL for bindings/audit/templates), outbox_repo get/mark/already_sent/sent_today/claim_for_send.

## Not done / limits
- Cloud Tasks mode raises NotImplementedError; `/tasks/*` routes need an admin login in local mode and answer 501 in cloud mode.
- Task handlers for `tap`, `ingest_event` and the `nudge-*` task only log (no agent intake, no delayed nudge).
- Reminder greeting uses "friend" (names live encrypted in the vault; no decrypt path wired).
- `binding_id` is the person_id (table key is person_id+channel). Supporter bindings have no patient_id.
- Governor patient token cap only tracks UUID patient ids. Seeded demo spend counts toward the event budget (CM_BUDGET_EVENT_USD).
- Free-text messages from the bot chat are enqueued only; no reply. Onboarding wizard, language commands are not built.
- Red draft recipients carry an empty `token` string.

## Polling mode (no public URL, no ngrok)
Use this on a laptop. A bot cannot poll while a webhook is set; the poller removes it at start (updates are kept).
1. In Telegram open t.me/sentience_caremem_bot. Get a code: `python -m cm.jobs.make_invite --patient PT-0142`
   (the live smoke wrote one to `caremem/out/telegram_invite.txt`; single use, 24 h). Send `/start CODE` to the bot.
2. `python -m cm.jobs.dev_telegram` (poller plus outbox drainer, Ctrl+C stops both). Needs Postgres up and `TELEGRAM_BOT_TOKEN` in `.env`.
   Poller alone: `python -m cm.jobs.tg_poll`. The offset is kept in `out/tg_offset.json` (override `TG_OFFSET_FILE`).
3. In another shell: `python -m cm.jobs.reminders --now`. The drainer sends it within 5 s. Tap Taken / Missed / Feeling unwell.
4. Quiet hours (21:00-07:00 IST) defer reminders. For the demo set `CM_ENV=dev` and `DEMO_IGNORE_QUIET_HOURS=1` in `.env`
   (ignored in any other CM_ENV) before running `reminders --now` and `dev_telegram`.
5. To go back to the webhook: `python scripts/tg_set_webhook.py` (stop the poller first).
Security: the poller calls `telegram.handle_local_poll` (trusted, no secret header; the nonce is per process and never leaves memory). The HTTP route does not import it. Logs carry update_id and type only; httpx request logging is muted because its URLs contain the token.
