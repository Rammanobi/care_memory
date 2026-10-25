# Lane M notes (Gmail, consent, calendar)

Env names only: GMAIL_OAUTH_CLIENT_JSON, GMAIL_REFRESH_TOKEN, GMAIL_MAILBOX, DOCTOR_EMAIL_ALLOWLIST,
GMAIL_PUBSUB_TOPIC, PUBSUB_PUSH_AUDIENCE, PUBSUB_PUSH_SA_EMAIL, GOOGLE_CALENDAR_ID.

Integrator wires the Protocols in `ports_gmail.py`: GmailApi, TaskQueue, GmailStateStore, TokenStore
(approval_tokens, sha256(T:n)), DecideFn (adapter to cm.review.decide), OutboxWriter (gmail_echo), AuditLog,
CalendarApi, ConsentStore. Fakes in `fakes_gmail.py`.

Not done: real googleapiclient adapter, OIDC verify (webhook route), LLM fallback parser, district report,
CSV/lab routing by plus-tag, Gmail label modify. Retry is local (`call_with_retry`) because cm.core.retry
was not ready; swap when stable. ALL expands until first token miss. Reject with no reason gets a default reason.
Edit payload is `{"body": text}`; visit edits may need `{"doctor_decision": ...}` per approval kind.

## Attachments entry point (library path, not wired)
`cm.channels.gmail_attach.dispatch(msg, on_reply=..., api=, allowlist=, resolve_doctor=, audit=)` is the
`on_message` for `gmail.fetch_worker`. A reply-like message (plus-tag token in To/Delivered-To, or In-Reply-To /
References a digest) always goes to `on_reply` first; attachments are handled in addition, never instead.
Inline signature images (Content-ID or inline disposition up to 100 KB, any image up to 10 KB) are dropped by
`gmail._attachments`. Patient code must be `PT-` plus exactly 4 digits. **No runtime caller exists yet**: the
inbound fetch loop is future work, so doctor email attachments are not ingested in the running system.
Known gap: `cm.uploads.intake.accept_upload` has no `author_role` argument, so the document row keeps its
default author role; pass the doctor role once the intake supports it.
