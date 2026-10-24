## Why
Gmail lane runs against fakes; a real adapter is needed for the live demo.

## What Changes
Add a real Gmail adapter (OAuth via env/Secret Manager, polling, decisions via `cm/review/decide.py`).

## Out of scope
Credentials in repo, sending without review.

## Owning lane
Gmail/Integration lane. No change to `cm/contracts/`.
