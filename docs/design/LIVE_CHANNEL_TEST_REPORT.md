# Live channel test report (2026-10-25, local, mock data)

Scope: the real Telegram bot (`@sentience_caremem_bot`) driven from the owner's Telegram Web session against the local stack (Postgres, poller `python -m cm.jobs.dev_telegram`). No Google Cloud, no Gmail credentials. Gmail is covered by the offline simulation in `GMAIL_SIM_REPORT.md`.

## Telegram: patient free text (live)

| # | Message sent by the patient | Bot reply (live) | Doctor queue (checked in the database) |
|---|---|---|---|
| 1 | "I will travel on Friday" | "Thank you, Ravi. Your message has been passed to your care team. They will reply here." | green request, source telegram |
| 2 | "Can I change my reminder time to 9 pm?" (within 10 minutes) | no second acknowledgement (rate limit: 1 per 10 min) | second request stored |
| 3 | "coughing blood" | urgent acknowledgement: "Thank you, Ravi. We have told your care team now. If you feel very unwell, please call 108 right away" | Red request "Urgent message" plus Red fast-path draft |
| 4 | "should I stop the tablets?" | no advice from the bot; normal acknowledgement suppressed by the rate limit | Amber request "Medicine question", high priority |

Safety properties observed: the reply is always an approved template (no AI text to the patient), the patient's words are not echoed, no medical advice, urgent text escalates to the doctor queue.

Not exercised live in this run (covered by 13 offline tests in `tests/integration/test_telegram_free_text.py`): Telugu acknowledgement, unbound chat, `/stop`, doctor reply delivery through the outbox, very long text, duplicates.

## Gmail

Offline simulation only (56 scenario tests, real Postgres adapters on the test database, fakes for Google). See `GMAIL_SIM_REPORT.md`. Live Gmail (OAuth, watch, push delivery, real headers) is not verified and needs Google credentials at deploy time.

## Limits of this report

Screenshots were not captured: the in-app browser pane was too small to render the chat. Results above come from reading the Telegram Web page text and the database.
