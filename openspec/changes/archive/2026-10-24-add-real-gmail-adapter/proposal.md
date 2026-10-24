## Why
Gmail lane runs against fakes; a real adapter is needed for the live demo.

## What Changes
Add a real Gmail adapter (OAuth via env/Secret Manager, polling, decisions via `cm/review/decide.py`).

## Out of scope
Credentials in repo, sending without review.

## Owning lane
Gmail/Integration lane. No change to `cm/contracts/`.

## Implemented locally (no Google credentials, no network)
Real adapter classes, OIDC push verification, Pg adapters (TokenStore, GmailStateStore, DecideFn via `cm.review.decide`), calendar sync job skeleton, `scripts/gmail_auth.py`. Message dedup is stored in `cm.audit_log` (no dedicated table; no migration added). Real-Google verification is owner-only (task 1.4).
