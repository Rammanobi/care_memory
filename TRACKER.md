# CareMemory: GitHub Repository Progress Tracker

**Progress summary (24 Oct 2026):** 12 of 16 feature slices done, 3 partial, 1 in progress (AI runtime). 207 Python tests and 14 web tests pass; the doctor gate is enforced by a database constraint. Still to land: AI runtime, memory engine, rules R1-R6, cloud deploy.

Back to the [README](README.md) · Web version: [docs/index.html](docs/index.html) · Rubric: [docs/design/EVALUATION_PLAN.md](docs/design/EVALUATION_PLAN.md)

Status words: **done** = code plus an automated test or a recorded check · **partial** = code exists, a piece is missing or only tested against fakes · **in progress** = another lane is building it today · **planned** = designed, not built.

---

## (a) Build order: feature slices

Points use the organisers' latest split: Round 1 = 40, Round 2 = 60 (rubric raw max 50, scaled x1.2: functionality 18, technical depth 12, UI/UX 6, completeness 6, viability 6, Q&A and team 6, presentation 6). "Points fed" is our estimate of which marks each slice supports; 37 of the 100 points come from the live presentation, Q&A and demo delivery and are not tied to any one slice.

| # | Slice | What it delivers | Main files / folders | Evidence | Status | Rubric criteria fed | Points fed (of 100) |
|---|---|---|---|---|---|---|---|
| F01 | Project scaffold | Python and Node tooling, lint and test config, agent rules, OpenSpec setup, dependency pin fix | `pyproject.toml`, `requirements*.txt`, `Makefile`, `CLAUDE.md`, `MEMORY.md`, `.claude/`, `openspec/config.yaml` | `tests/test_smoke.py` passes; archived `fix-tenacity-pin-conflict` | done | Q&A and team | 1 |
| F02 | Contracts and module skeletons | Frozen Pydantic contracts (`contracts-v1`) shared by every lane; empty modules for memory, rules, sim, eval, RAG | `cm/contracts/`, stubs in `cm/memory/`, `cm/rules/`, `cm/sim/`, `cm/eval/`, `cm/rag/` | contracts import in every test run | done (skeleton modules are planned features) | Technical depth | 2 |
| F03 | Infra | Docker image, local Postgres 16 + pgvector compose, numbered GCP scripts, Cloud Build | `Dockerfile`, `docker-compose.yml`, `infra/`, `.env.example` | `docker compose up -d db` running on port 5433 | partial (GCP not deployed) | Viability | 2 |
| F04 | Data core and event store | Config, DB pool, sim-aware clock, ids, logging; 7 migrations; append-only events; repositories | `cm/core/` (base), `cm/store/`, `cm/jobs/migrate.py` | `tests/unit/core`, `tests/integration/test_repos.py` | done | Functionality, Technical depth | 4 |
| F05 | Doctor decision service | `decide()`: one transaction for decision plus outbox rows; DB doctor-gate `CHECK` and trigger enforced | `cm/review/decide.py`, `0002_reliability.sql` | `tests/integration/test_decide.py` | done | Functionality, Technical depth, Viability | 7 |
| F06 | Core API and seed | Auth (scrypt, JWT cookie, rate limits), review queue, bulk decision, patients, timeline, portal routes, dashboard, admin, banned-term response filter, deterministic seed 42; backend gaps (SSE stream, district, dose undo, documents) | `cm/api/`, `cm/jobs/seed*.py` | `tests/integration/test_e2e_api.py`, `test_seed.py`, `tests/unit/api`; `GET /healthz` ok | done (gaps work in progress today) | Functionality, Technical depth, Completeness | 7 |
| F07 | AI budget governor | GREEN/AMBER/RED states, demo reserve, circuit breaker, retry with retry-after, governed `get_model`, PII tokeniser | `cm/core/budget.py`, `budget_pg.py`, `llm.py`, `retry.py`, `tokenize.py` | `tests/unit/core_ai/test_ai.py` | done (not tested against live providers) | Technical depth, Viability | 4 |
| F08 | Content | 12 approved EN/TE templates, text bank, banned-term scanner | `cm/router/templates/`, `fixtures/text_bank.json`, `scripts/banned_terms.py` | `tests/unit/content/`; scanner clean | done (Telugu needs native review) | UI/UX, Viability | 2 |
| F09 | Telegram lane | Webhook (secret, dedupe, event first), fast path to Red draft, router, quiet hours, gated sender | `cm/channels/tg_*.py`, `cm/router/` | `tests/unit/channels/` (23 tests) | done (against fakes) | Functionality, Completeness | 4 |
| F10 | Gmail lane | Digest, "approve 1" reply parser, single-use tokens, consent flows, calendar visits, channel fallback | `cm/channels/gmail*.py`, `calendar.py`, `consent_flows.py` | `tests/unit/gmail/` | partial (no real Google client yet) | Functionality, Completeness | 2 |
| F11 | Telegram live wiring | Postgres adapters, httpx client, `/webhooks/telegram`, outbox drainer, daily reminders, invite codes, local task queue | `cm/channels/adapters_pg.py`, `tg_http.py`, `cm/jobs/outbox_drainer.py`, `reminders.py` | `tests/integration/test_telegram_pg.py` | partial (live bot run is an owner step) | Functionality | 2 |
| F12 | Doctor console | Today, Patients, patient page, Approvals with SLA and bulk approve, Requests, Ask, Memory Lens, District, Admin caps, Settings | `web/src/pages/`, `web/src/components/` | screenshots in `docs/assets/ui/` | done (screens; Lens and District on sample data) | Functionality, UI/UX, Completeness | 6 |
| F13 | Patient app and Supporter view | Welcome and consent, home, record, messages, ask, me, help, privacy; Telugu; Supporter tap | `web/src/pages/PatientApp/`, `web/src/pages/Supporter/` | screenshots; banned-term scan of these folders | done (screens) | UI/UX, Completeness | 3 |
| F14 | Web on the real API | HTTP adapter, real login, role guards, SSE with polling fallback, offline banner, portal data | `web/src/api/`, `web/src/realtime/` | `web/src/api/mapping.test.ts` (14 tests) | done (adapter round 3 in progress today) | Functionality | 1 |
| F15 | AI runtime | Deep Agents orchestrator, narrator and drafter, `interrupt()` at `submit_for_review`, cite-or-cut, LLM Ask box, nightly job | `cm/agents/`, `cm/tools/`, `cm/validator/`, `cm/api/routers/query.py` | change `add-ai-runtime` open; tests being written in `tests/unit/ai/` | in progress | Technical depth, Completeness | 2 |
| F16 | Documentation | README, this tracker, web page, design docs, diagrams, screenshots | `README.md`, `TRACKER.md`, `docs/` | diagrams render with Mermaid 11.4.1; page screenshot checked | done | Round 1, Q&A and team, Presentation | 14 |
| | **Total tied to slices** | | | | | | **63** |

Not built yet (no slice until they land): memory engine (beliefs, detectors, risk with interval), rules R1 to R6, identity matcher, RAG guidelines, simulator and 60-day evaluation, sweeper, Cloud Tasks mode, GCP deployment. See (c).

## (b) Git commit plan: one commit per slice

Rules for the person committing:
- Run from `caremem/`, in the order below (dependency order). Commits are made today with real timestamps; never rewrite or fake dates.
- Each `git add` line was dry-run checked on 24 Oct 2026 (`git add --dry-run`). Lines marked "only if present" cover files other lanes may still be creating; they are harmless when the path does not exist.
- After the last commit, `git status --porcelain` must print nothing. If a new file appears (another lane added it after this plan was written), add it to the slice that owns its folder in a follow-up commit, for example `git commit -m "feat(api): add <thing>"`.
- Check for secrets before any push: `git diff --cached --name-only | grep -E '(^|/)\.env$'` must be empty, and `git grep -nE "sk-[A-Za-z0-9]{20,}|BEGIN PRIVATE"` must find nothing.
- Every committable file maps to exactly one slice (checked with a script against `git ls-files --others --exclude-standard`: 0 unassigned, 0 duplicates at the time of writing).

#### F01: chore: scaffold project, agent rules and OpenSpec tooling
```bash
git add -- .gitignore .gitattributes .dockerignore pyproject.toml requirements.txt requirements-dev.txt Makefile CLAUDE.md MEMORY.md package.json package-lock.json .claude/ openspec/config.yaml openspec/specs/.gitkeep openspec/changes/archive/.gitkeep openspec/changes/archive/2026-10-23-fix-tenacity-pin-conflict/ cm/__init__.py tests/conftest.py tests/test_smoke.py tests/unit/__init__.py
git commit -m "chore: scaffold project, agent rules and OpenSpec tooling"
```

#### F02: feat(contracts): add frozen contracts and module skeletons
```bash
git add -- cm/contracts/ tests/contract/ cm/identity/ cm/memory/ ':(exclude)cm/memory/features.py' cm/rules/ cm/sim/ cm/eval/ cm/rag/ cm/observability/ cm/security/ cm/jobs/eval_job.py cm/channels/chemist_csv.py cm/channels/portal_mock.py cm/channels/wearable_mock.py tests/redteam/ tests/replay/ tests/unit/identity/ tests/unit/rules/ tests/unit/sim/ tests/unit/eval/ tests/unit/rag/ tests/unit/observability/ tests/unit/security/
git commit -m "feat(contracts): add frozen contracts and module skeletons"
```

#### F03: build(infra): add Docker image, local compose and GCP deploy scripts
```bash
git add -- Dockerfile docker-compose.yml .env.example infra/ scripts/ngrok_dev.sh scripts/seed_local.sh
git commit -m "build(infra): add Docker image, local compose and GCP deploy scripts"
```

#### F04: feat(store): add data core, append-only event store and migrations
```bash
git add -- cm/core/ ':(exclude)cm/core/budget.py' ':(exclude)cm/core/budget_pg.py' ':(exclude)cm/core/llm.py' ':(exclude)cm/core/retry.py' ':(exclude)cm/core/tokenize.py' ':(exclude)cm/core/lifecycle.py' ':(exclude)cm/core/NOTES_ai.md' ':(exclude)cm/core/tasks.py' cm/store/ ':(exclude)cm/store/ai_repo.py' cm/jobs/__init__.py cm/jobs/migrate.py tests/unit/core/ tests/unit/store/ tests/integration/__init__.py tests/integration/conftest.py tests/integration/test_repos.py
git commit -m "feat(store): add data core, append-only event store and migrations"
```

#### F05: feat(review): add single decide() transaction behind the DB doctor gate
```bash
git add -- cm/review/ tests/unit/review/ tests/integration/test_decide.py
git commit -m "feat(review): add single decide() transaction behind the DB doctor gate"
```

#### F06: feat(api): add core API, auth, doctor and portal routes, deterministic seed
```bash
git add -- cm/api/ ':(exclude)cm/api/routers/query.py' ':(exclude)cm/api/routers/webhooks.py' ':(exclude)cm/api/routers/tasks.py' cm/jobs/seed.py cm/jobs/seed_data.json cm/jobs/seed_events.py cm/jobs/seed_ops.py cm/jobs/seed_patient_app.py cm/jobs/seed_review.py tests/unit/api/ tests/unit/jobs/ tests/integration/test_e2e_api.py tests/integration/test_seed.py ':(glob)tests/integration/test_gaps*.py' openspec/changes/archive/2026-10-24-add-backend-slice-1/ openspec/specs/backend-api/ ':(glob)openspec/changes/archive/*-add-backend-gaps-1/**'
git add -- openspec/changes/add-backend-gaps-1/ 2>/dev/null || true   # only if present at commit time
git commit -m "feat(api): add core API, auth, doctor and portal routes, deterministic seed"
```

#### F07: feat(core): add AI budget governor, retry, governed get_model and PII tokeniser
```bash
git add -- cm/core/budget.py cm/core/budget_pg.py cm/core/llm.py cm/core/retry.py cm/core/tokenize.py cm/core/lifecycle.py cm/core/NOTES_ai.md tests/unit/core_ai/ openspec/changes/archive/2026-10-24-add-ai-budget-governor/ openspec/specs/ai-budget/
git commit -m "feat(core): add AI budget governor, retry, governed get_model and PII tokeniser"
```

#### F08: feat(content): add EN/TE message templates, text bank and banned-term scanner
```bash
git add -- cm/router/templates/ fixtures/text_bank.json scripts/banned_terms.py data/guidelines/ tests/unit/content/ openspec/changes/archive/2026-10-24-add-content-templates/ openspec/specs/content/
git commit -m "feat(content): add EN/TE message templates, text bank and banned-term scanner"
```

#### F09: feat(telegram): add webhook intake, fast path, router and gated sender
```bash
git add -- cm/channels/__init__.py cm/channels/telegram.py cm/channels/tg_callback.py cm/channels/tg_client.py cm/channels/tg_fakes.py cm/channels/tg_inbound.py cm/channels/tg_ratelimit.py cm/channels/tg_sender.py cm/channels/binding.py cm/channels/supporter_web.py cm/channels/ports.py cm/channels/sim_updates.py cm/channels/household.py cm/channels/factory.py cm/channels/webpush.py cm/channels/NOTES.md cm/router/ ':(exclude)cm/router/templates/' ':(exclude)cm/router/degrade.py' tests/unit/channels/ tests/unit/router/ openspec/changes/archive/2026-10-24-add-telegram-lane/ openspec/specs/telegram-channel/
git commit -m "feat(telegram): add webhook intake, fast path, router and gated sender"
```

#### F10: feat(gmail): add digest, approve-by-reply parser, consent flows and calendar
```bash
git add -- cm/channels/gmail.py cm/channels/gmail_parse.py cm/channels/gmail_reply.py cm/channels/calendar.py cm/channels/consent_flows.py cm/channels/ports_gmail.py cm/channels/fakes_gmail.py cm/channels/NOTES_gmail.md cm/router/degrade.py tests/unit/gmail/ openspec/changes/archive/2026-10-24-add-gmail-lane/ openspec/specs/gmail-lane/
git commit -m "feat(gmail): add digest, approve-by-reply parser, consent flows and calendar"
```

#### F11: feat(telegram): wire live bot with Postgres adapters, outbox drainer and reminders
```bash
git add -- cm/channels/adapters_pg.py cm/channels/tg_http.py cm/channels/NOTES_integration.md cm/core/tasks.py cm/api/routers/webhooks.py cm/api/routers/tasks.py cm/jobs/outbox_drainer.py cm/jobs/reminders.py cm/jobs/make_invite.py cm/jobs/tg_set_webhook.py scripts/tg_set_webhook.py scripts/set_telegram_webhook.sh tests/integration/test_telegram_pg.py openspec/changes/archive/2026-10-24-add-telegram-integration/ openspec/specs/telegram-integration/
git commit -m "feat(telegram): wire live bot with Postgres adapters, outbox drainer and reminders"
```

#### F12: feat(web): add doctor console screens on mock data
```bash
git add -- web/.env.example web/index.html web/package.json web/package-lock.json web/postcss.config.js web/tailwind.config.js web/tsconfig.json web/vite.config.ts web/src/main.tsx web/src/router.tsx web/src/components/ web/src/styles/ web/src/mocks/ web/src/auth/ web/src/pages/ ':(exclude)web/src/pages/PatientApp/' ':(exclude)web/src/pages/Supporter/' openspec/changes/archive/2026-10-24-add-web-doctor-patient-ui/ openspec/changes/archive/2026-10-24-add-doctor-screens/ openspec/specs/web-ui/ openspec/specs/doctor-console/
git commit -m "feat(web): add doctor console screens on mock data"
```

#### F13: feat(web): add patient app and Supporter view in English and Telugu
```bash
git add -- web/src/pages/PatientApp/ web/src/pages/Supporter/ web/src/supporter/ openspec/changes/archive/2026-10-24-add-patient-supporter-screens/ openspec/specs/patient-app/
git commit -m "feat(web): add patient app and Supporter view in English and Telugu"
```

#### F14: feat(web): add real HTTP adapter, login, live updates and portal data
```bash
git add -- web/src/api/ web/src/realtime/ openspec/changes/archive/2026-10-24-add-web-http-adapter/ openspec/changes/archive/2026-10-24-add-web-portal-http-data/ openspec/specs/web-http-adapter/ openspec/specs/web-portal-http/ openspec/changes/add-web-adapter-3/
git add -- web/dev-server/ 2>/dev/null || true   # only if present at commit time
git add -- ':(glob)openspec/changes/archive/*-add-web-adapter-3/**' 2>/dev/null || true   # only if present at commit time
git commit -m "feat(web): add real HTTP adapter, login, live updates and portal data"
```

#### F15: feat(ai): add Deep Agents runtime, narrator, cite-or-cut and LLM Ask box
```bash
git add -- cm/agents/ cm/tools/ cm/validator/ cm/memory/features.py cm/store/ai_repo.py cm/jobs/nightly.py cm/jobs/sweeper.py cm/api/routers/query.py tests/unit/ai/ tests/unit/agents/ tests/unit/tools/ tests/unit/validator/ tests/unit/memory/ openspec/changes/add-ai-runtime/
git add -- cm/jobs/ai_smoke.py 2>/dev/null || true   # only if present at commit time
git add -- ':(glob)openspec/changes/archive/*-add-ai-runtime/**' 2>/dev/null || true   # only if present at commit time
git add -- openspec/specs/ai-runtime/ 2>/dev/null || true   # only if present at commit time
git commit -m "feat(ai): add Deep Agents runtime, narrator, cite-or-cut and LLM Ask box"
```

#### F16: docs: add README, progress tracker, design docs, diagrams and screenshots
```bash
git add -- README.md docs/ openspec/changes/add-readme-and-tracker/
git add -- TRACKER.md 2>/dev/null || true   # only if present at commit time
git add -- ':(glob)openspec/changes/archive/*-add-readme-and-tracker/**' 2>/dev/null || true   # only if present at commit time
git commit -m "docs: add README, progress tracker, design docs, diagrams and screenshots"
```

### Must NOT be committed

All of these are already covered by `.gitignore`; check `git status` anyway.

| Path or pattern | Why |
|---|---|
| `.env`, `.env.*` (except `.env.example`, `web/.env.example`) | Real keys, tokens and demo passwords |
| `*.pem`, `*.key`, `client_secret*.json` | Credentials |
| `node_modules/`, `web/node_modules/` | Installed packages |
| `web/dist/`, `dist/`, `build/` | Build output |
| `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `.venv/` | Caches and virtualenvs |
| `out/`, `*.log`, `fixtures/snapshots/*.dump`, `*.pdf` | Generated output and local DB dumps |
| Docker volume `pgdata` | Local database data (lives in Docker, not in the repo) |

## (c) Next and not done

| Priority | Item | Owner lane | Why it matters for Round 2 |
|---|---|---|---|
| P0 | Finish and archive `add-ai-runtime`: narrator card, cite-or-cut, orchestrator `interrupt()`, LLM Ask box | E, N, D | Functionality 18 and technical depth 12 |
| P0 | Fix the TypeScript error in `web/src/api/httpAdapter.ts` (bulk result type) seen on 24 Oct; adapter round 3 is open | H1 | `npm run build` must pass for the demo |
| P0 | Rehearse the core loop on the real stack: patient request, doctor approves, patient sees "doctor approved"; Telegram tap to Red draft | all | Working demo |
| P1 | Memory engine v1 (missed-dose features, weekday pattern, refill gap) feeding Memory Lens and patient rows | C | Day 3 vs Day 60 claim from real data |
| P1 | Rules R1 to R6 reconciler, including household contact screening | D | Contradiction flags with cited evidence |
| P1 | Live Telegram bot run with the owner's token; record a backup video | F | Integration evidence |
| P1 | Deploy to Cloud Run with min instances 1 | I | Viability and deployment readiness |
| P2 | Real Gmail client and OIDC check on Pub/Sub push | M | Second channel |
| P2 | Simulator plus 60-day evaluation with calibration plot | B, J | Expected output in the problem statement |
| P2 | Red-team prompt-injection suite, replay cassettes for offline demo | D, J | Safety story |
| P3 | Native-speaker review of Telugu templates; Hindi | K | Usability |

## (d) One-line progress

12 of 16 feature slices done, 3 partial, 1 in progress (AI runtime). 207 Python tests and 14 web tests pass; the doctor gate is enforced by a database constraint. Still to land: AI runtime, memory engine, rules R1-R6, cloud deploy.
