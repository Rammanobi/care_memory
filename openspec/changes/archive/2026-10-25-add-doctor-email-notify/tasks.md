## 1. Implementation
- [x] 1.1 `cm/store/gmail_repo.py`: doctor_notify_claim / release (test: test_pg_store_claim_throttle_duplicate)
- [x] 1.2 `cm/channels/doctor_notify.py`: render, modes, throttle, send via GmailApi port, CLI (tests/unit/channels/test_doctor_notify.py)
- [x] 1.3 `.env.example`: names and placeholders only
## 2. Verification
- [x] 2.1 23 offline tests + 1 db test pass; ruff clean
