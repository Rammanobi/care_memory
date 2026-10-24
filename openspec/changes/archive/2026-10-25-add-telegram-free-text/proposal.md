## Why
A patient who typed free text to the Telegram bot got no reply and the message never reached a doctor (it was only enqueued and logged).

## What Changes
Owning lane: F (cm/channels/tg_*), with owner-authorised touches in K's template YAML and Lane A's channels_repo. Implements `telegram-channel` free-text handling.
- Free text from a bound patient chat is saved as a ContextNote event and as a doctor-visible request (approvals, subkind patient_request, source telegram), same flow as the web "message to my care team".
- ONE pre-approved template ack (telegram_ack_v1, EN or TE), sent inline, max 1 per person per 10 minutes. Danger text gets telegram_ack_urgent_v1 (adds "call 108").
- Danger words (EN, TE) create a Red request plus the existing red fast-path draft. Medicine-advice questions create an Amber high-priority request. The system never answers content.
- The doctor's reply goes through decide() and the gated outbox to Telegram. Unbound chats get "by invitation"; after /stop nothing is stored or acked.
- Out of scope: supporter chats, non-text messages, onboarding wizard, any AI-written reply. No contract changes (ContextNote already exists).
