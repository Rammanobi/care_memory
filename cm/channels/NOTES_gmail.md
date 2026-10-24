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
