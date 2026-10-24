## Why
The owner needs three demo patient logins with 3, 30 and 60 days of mock history (plus a Supporter for the 30-day patient) to show how memory and RAG answers differ with history length, and the same accounts must be re-creatable on Cloud SQL.

## What Changes
- New job `python -m cm.jobs.seed_demo_accounts`: additive, idempotent, deterministic (seeds 9007/9030/9060, day0 2026-08-27, as_of sim day 59). Codes PT-0903 (3 days, steady, en), PT-0930 (30 days, market-day misses, te, Supporter S-93), PT-0960 (60 days, payday misses, en). Users demo.pt0903, demo.pt0930, demo.pt0960, demo.sup0930.
- Runs memory pipeline and rag_index per demo patient (real embeddings only when OPENAI_API_KEY is set and `--no-embed` is absent).
- `--export` / `--import` portable JSON bundle (no passwords).
- Passwords from env `DEMO_ACCOUNT_PASSWORDS` or git-ignored `out/demo_accounts_credentials.txt`; never printed.
- Refuses unless `CM_DATA_CLASS=mock`.

Out of scope: touching PT-0142, Telegram bindings, web/, Dockerfile, infra/, cm/rag/, cm/api/main.py, contracts. Owning lane: B (seed). Implements the demo/eval data requirement from the owner.

## Impact
New files only: `cm/jobs/seed_demo_accounts.py`, `tests/unit/jobs/test_seed_demo_accounts.py`. No contract change.
