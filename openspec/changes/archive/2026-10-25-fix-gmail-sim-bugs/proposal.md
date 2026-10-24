## Why
Gmail end-to-end simulation (tests/integration/test_gmail_sim_e2e.py) found three real bugs. Lane M (Gmail); touches cm/store/gmail_repo.py with one read helper. No contract change.

## What Changes
- Symptom/root cause/fix 1: HTML-only replies parsed as empty (gmail._plain_text ignored text/html); now falls back to tag-stripped HTML.
- 2: decide() refusals (banned_term, reason_required) consumed the single-use token; gmail_reply._apply now releases it.
- 3: a token for an item escalated to Red after the digest allowed an email approve; PgDecide refuses via='gmail' on Red (red_not_bulk) using gmail_repo.approval_tier.

Out of scope: allowlist routing, PG consent adapter. Verified by the sim (56 tests) and tests/unit/gmail (65).
