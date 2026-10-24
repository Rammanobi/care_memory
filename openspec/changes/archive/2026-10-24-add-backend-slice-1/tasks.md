## 1. Core and store
- [x] 1.1 cm/core config, db, clock, ids (tests/unit/core)
- [x] 1.2 migrate runner (cm/jobs/migrate.py) and migrations 0001..0007 applied
- [x] 1.3 store repos (tests/integration/test_repos.py)
## 2. Decision
- [x] 2.1 cm/review/decide.py (tests/integration/test_decide.py)
## 3. API
- [x] 3.1 auth, deps, suppress (tests/unit/api)
- [x] 3.2 routers: review, requests, dashboard, query, admin, portal
- [x] 3.3 end-to-end test (tests/integration/test_e2e_api.py)
## 4. Seed
- [x] 4.1 cm/jobs/seed.py idempotent (tests/integration/test_seed.py)
## 5. Verify
- [x] 5.1 ruff clean, pytest green, curl checks
