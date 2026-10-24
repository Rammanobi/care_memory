## 1. Implementation
- [x] 1.1 Adapter: `cm/channels/gmail_google.py` (GoogleGmailApi, GoogleCalendarApi, lazy, error mapping; retry stays in `gmail.call_with_retry`). Tests: `tests/unit/gmail/test_gmail_real.py` (injected services, HttpMock)
- [x] 1.2 OAuth setup: `scripts/gmail_auth.py` (one-time consent helper, not run); env names only; pins verified on PyPI in `requirements.txt`
- [x] 1.3 Push OIDC verify `cm/channels/gmail_oidc.py` (local RSA test keys); DB adapters `cm/channels/adapters_gmail_pg.py` + `cm/store/gmail_repo.py`; `sync_calendar_events` skeleton in `cm/channels/calendar.py`
- [ ] 1.4 Owner-only: run `scripts/gmail_auth.py`, set env, live smoke (send, watch, push, reply "approve 1")
- [ ] 1.5 Integrator: wire webhook route to `verify_push_jwt` + `google_cert_fetcher`, `/tasks/calendar-sync` to `sync_calendar_events`, and factory construction of the Pg adapters
