## Why
The owner's final demo requirement is exactly two demo patient accounts with mock data: a 6-day account and a 60-day account. Three exist (PT-0903, PT-0930 + Supporter, PT-0960).

## What Changes
- Default demo set becomes PT-0906 (6 days, login demo.pt0906, English, steady adherer, seed 9006) and PT-0960 (unchanged).
- New `--retire-extra` (default on): disables the logins of the earlier extras (demo.pt0903, demo.pt0930, Supporter demo.sup0930) via `cm.store.auth_repo.disable_login` (active=false, token_version+1, so live sessions die too). Idempotent; no-op where the users do not exist. No data is deleted.
- Patients PT-0903 and PT-0930 are NOT hidden from the doctor list: the schema has no supported hide state (`patients.status` values are active/records_only/paused/completed/erased; readmodels filters only `erased`, which means DPDP erasure and is not used). Reported to the owner.
- `scripts/make_demo_env.py` ROLES lists the two demo patients only.

Out of scope: schema changes, readmodels, README/TRACKER/html, the live database run. Owning lane: B (seed) with a small `cm/store` addition (lane A). No contract change.

## Impact
`cm/jobs/seed_demo_accounts.py`, new `cm/store/auth_repo.py`, `tests/unit/jobs/test_seed_demo_accounts.py`, `scripts/make_demo_env.py`.
