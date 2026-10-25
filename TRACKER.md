# CareMemory: GitHub Repository Progress Tracker

**Progress summary (25 Oct 2026, about 02:30 IST):** 23 of 29 feature slices done, 6 partial, 0 in progress, 0 planned, plus the post-F29 slices below. Backend 1967 passed, 2 skipped, 3 xfailed (expected failures, known gaps); web typecheck OK, 241 tests pass, build OK; the doctor gate is enforced by a database constraint. Deployment to Google Cloud is planned for 2026-10-25 and has NOT happened. Plan: [docs/deploy/DEPLOY_PLAN.md](docs/deploy/DEPLOY_PLAN.md).

Back to the [README](README.md) · Web version: [docs/index.html](docs/index.html) · Rubric: [docs/design/EVALUATION_PLAN.md](docs/design/EVALUATION_PLAN.md)

Status words: **done** = code plus an automated test or a recorded check · **partial** = code exists, a piece is missing or only tested against fakes or not yet verified live · **in progress** = another lane is building it right now (none at the moment) · **planned** = designed, not built.

---

## (a) Build order: feature slices

Points use the organisers' latest split: Round 1 = 40, Round 2 = 60 (rubric raw max 50, scaled x1.2: functionality 18, technical depth 12, UI/UX 6, completeness 6, viability 6, Q&A and team 6, presentation 6). "Points fed" is our estimate of which marks each slice supports; 37 of the 100 points come from the live presentation, Q&A and demo delivery and are not tied to any one slice.

| # | Slice | What it delivers | Main files / folders | Evidence | Status | Rubric criteria fed | Points fed (of 100) |
|---|---|---|---|---|---|---|---|
| F01 | Project scaffold | Python and Node tooling, lint and test config, agent rules, OpenSpec setup, dependency pin fix | `pyproject.toml`, `requirements*.txt`, `Makefile`, `CLAUDE.md`, `MEMORY.md`, `.claude/`, `openspec/config.yaml` | `tests/test_smoke.py` passes; archived `fix-tenacity-pin-conflict` | done | Q&A and team | 1 |
| F02 | Contracts and module skeletons | Frozen Pydantic contracts (`contracts-v1`) shared by every lane; empty modules for memory, rules, sim, eval, RAG | `cm/contracts/`, stubs in `cm/memory/`, `cm/rules/`, `cm/sim/`, `cm/eval/`, `cm/rag/` | contracts import in every test run | done (skeleton modules are planned features) | Technical depth | 2 |
| F03 | Infra | Docker image, local Postgres 16 + pgvector compose, numbered GCP scripts, Cloud Build | `Dockerfile`, `docker-compose.yml`, `infra/`, `.env.example` | `docker compose up -d db` running on port 5433 | partial (GCP not deployed; production image is F26) | Viability | 2 |
| F04 | Data core and event store | Config, DB pool, sim-aware clock, ids, logging; 7 migrations; append-only events; repositories | `cm/core/` (base), `cm/store/`, `cm/jobs/migrate.py` | `tests/unit/core`, `tests/integration/test_repos.py` | done | Functionality, Technical depth | 4 |
| F05 | Doctor decision service | `decide()`: one transaction for decision plus outbox rows; DB doctor-gate `CHECK` and trigger enforced | `cm/review/decide.py`, `0002_reliability.sql` | `tests/integration/test_decide.py` | done | Functionality, Technical depth, Viability | 7 |
| F06 | Core API and seed | Auth (scrypt, JWT cookie, rate limits), review queue, bulk decision, patients, timeline, portal routes, dashboard, admin, banned-term response filter, deterministic seed 42; backend gaps (SSE stream, district, dose undo, documents) | `cm/api/`, `cm/jobs/seed*.py` | `tests/integration/test_e2e_api.py`, `test_seed.py`, `tests/unit/api`; `GET /healthz` ok | done (backend gaps closed; later fixes in F20) | Functionality, Technical depth, Completeness | 7 |
| F07 | AI budget governor | GREEN/AMBER/RED states, demo reserve, circuit breaker, retry with retry-after, governed `get_model`, PII tokeniser | `cm/core/budget.py`, `budget_pg.py`, `llm.py`, `retry.py`, `tokenize.py` | `tests/unit/core_ai/test_ai.py` | done (live provider runs on mock data are recorded under F15, F19 and F23) | Technical depth, Viability | 4 |
| F08 | Content | 12 approved EN/TE templates, text bank, banned-term scanner | `cm/router/templates/`, `fixtures/text_bank.json`, `scripts/banned_terms.py` | `tests/unit/content/`; scanner clean | done (Telugu needs native review) | UI/UX, Viability | 2 |
| F09 | Telegram lane | Webhook (secret, dedupe, event first), fast path to Red draft, router, quiet hours, gated sender | `cm/channels/tg_*.py`, `cm/router/` | `tests/unit/channels/` (23 tests) | done (against fakes) | Functionality, Completeness | 4 |
| F10 | Gmail lane | Digest, "approve 1" reply parser, single-use tokens, consent flows, calendar visits, channel fallback | `cm/channels/gmail*.py`, `calendar.py`, `consent_flows.py` | `tests/unit/gmail/` | partial (no real Google client yet) | Functionality, Completeness | 2 |
| F11 | Telegram live wiring | Postgres adapters, httpx client, `/webhooks/telegram`, outbox drainer, daily reminders, invite codes, local task queue | `cm/channels/adapters_pg.py`, `tg_http.py`, `cm/jobs/outbox_drainer.py`, `reminders.py` | `tests/integration/test_telegram_pg.py` | partial (live bot run is an owner step) | Functionality | 2 |
| F12 | Doctor console | Today, Patients, patient page, Approvals with SLA and bulk approve, Requests, Ask, Memory Lens, District, Admin caps, Settings | `web/src/pages/`, `web/src/components/` | screenshots in `docs/assets/ui/` | done (screens; Lens and District on sample data) | Functionality, UI/UX, Completeness | 6 |
| F13 | Patient app and Supporter view | Welcome and consent, home, record, messages, ask, me, help, privacy; Telugu; Supporter tap | `web/src/pages/PatientApp/`, `web/src/pages/Supporter/` | screenshots; banned-term scan of these folders | done (screens) | UI/UX, Completeness | 3 |
| F14 | Web on the real API | HTTP adapter, real login, role guards, SSE with polling fallback, offline banner, portal data | `web/src/api/`, `web/src/realtime/` | `web/src/api/mapping.test.ts` (14 tests) | done (typecheck and build pass; 154 web tests) | Functionality | 1 |
| F15 | AI runtime | Deep Agents orchestrator, narrator and drafter, `interrupt()` at `submit_for_review`, cite-or-cut, LLM Ask box, nightly job | `cm/agents/`, `cm/tools/`, `cm/validator/`, `cm/api/routers/query.py` | `tests/unit/ai/`; live run on mock data with DeepSeek (commit f3a9663) | done (mock data only) | Technical depth, Completeness | 2 |
| F16 | Documentation | README, this tracker, web page, design docs, diagrams, screenshots | `README.md`, `TRACKER.md`, `docs/` | diagrams render with Mermaid 11.4.1; page screenshot checked | done | Round 1, Q&A and team, Presentation | 14 |
| F17 | Rules R1-R6 reconciler | Rules R1 to R6 including household contact screening, with red-team tests | `cm/rules/`, `tests/redteam/` | `tests/unit/rules/`, red-team tests (commit 3836d3b) | done | Functionality, Technical depth | n/a |
| F18 | Memory engine v1, nightly pipeline, conflicts | Features, detectors, belief lifecycle, risk interval; nightly memory pipeline, conflicts and persistence | `cm/memory/` | `tests/unit/memory/` (commits 909dddd, 5b073e6) | done (risk uses fixed documented weights, ECE 0.22 at day 60) | Technical depth, Functionality | n/a |
| F19 | AI eval suite and guards | AI eval suite (97 offline cases), narrator and Ask-box guards, shared banned-term lexicon | `cm/eval/`, `cm/validator/` | `docs/design/AI_EVAL_REPORT.md` (commit 55d29d3) | done (2 expected failures are known gaps) | Technical depth, Viability | n/a |
| F20 | Edge-case and invariant fixes | 19 real bugs found by property, concurrency, contract and edge-case suites, all fixed | across `cm/`, `tests/` | property, concurrency, contract and edge-case tests (commit 82bd17f) | done | Technical depth | n/a |
| F21 | Vision document extraction | DeepSeek vision extraction of documents into drafts for doctor review (mock data only) | see `openspec/specs/vision-extract/` | `openspec/specs/vision-extract/` (commit 650152a) | done (mock data only) | Functionality | n/a |
| F22 | Real Gmail and Calendar adapter | Real Gmail and Calendar adapter with push verification | `cm/channels/` | tested offline (commit d7aafb1); live Google verification pending | partial | Functionality, Completeness | n/a |
| F23 | Patient memory RAG | OpenAI `text-embedding-3-small` (1536d), hybrid BM25 + vector with RRF, MMR, no rerank, cite-or-cut `D-` citations; web citation chips | `cm/rag/`, `cm/eval/`, `web/src/` | RAG live eval: 66 questions, abstain accuracy 98.5%, groundedness 96.4%, judge pass 95.5%, 0 temporal leakage, citation validity 1.0 (commits e625106, f89639f) | done (DeepSeek flash, mock data; 3 model-side misses) | Technical depth, Functionality | n/a |
| F24 | Honest live-mode patient app | Patient app and patient-page Ask that show real data in live mode, with citation chips | `web/src/pages/PatientApp/` | web tests (commits 9d1bedd, bfe8f7a) | done | UI/UX, Functionality | n/a |
| F25 | Demo accounts | Deterministic demo accounts at 3, 30 and 60 days | see `openspec/specs/demo-accounts/` | `openspec/specs/demo-accounts/` (commit 8db6687) | done | Functionality | n/a |
| F26 | Production image and Cloud Tasks mode | Production image, Cloud Tasks mode, task auth and deploy scripts (local only, NOT deployed) | `Dockerfile`, `infra/`, `cm/core/tasks.py` | `openspec/specs/cloud-tasks/`, `openspec/specs/deployment/` (commit a46c2f3) | partial (not deployed) | Viability | n/a |
| F27 | Telegram free text to the doctor queue | Free text on a bound chat is stored and creates a doctor request (source telegram); ONE approved-template acknowledgement (EN/TE; 1 per patient per 10 min; urgent variant adds the 108 line); danger words go to the Red fast path; medicine-advice questions become Amber high priority; never answered by the system; unbound chat gets "by invitation"; after `/stop` nothing is stored | `cm/channels/`, `cm/router/templates/` | 13 offline tests; verified live on the real bot on 25 Oct (normal text acknowledged, rate limit, urgent text escalated) (commit c9ad3fd) | done (live Telugu and `/stop` paths not exercised live) | Functionality, Completeness | n/a |
| F28 | Gmail channel simulation | 55 scenario tests (56 tests) over the real Postgres adapters with fakes: digest, 32 reply cases, Pub/Sub push, calendar, consent, quiet hours; 3 bugs fixed (HTML-only replies, token burned by a refused decision, Red escalated after the digest approvable by email, so Red now needs the console) | `cm/channels/`, `tests/` | [GMAIL_SIM_REPORT.md](docs/design/GMAIL_SIM_REPORT.md) (commit cf62004); one real test email sent with the owner's approval (doctor notification check) and received | partial (fakes only; live Gmail inbound and push and Calendar NOT verified against real Google) | Functionality, Technical depth | n/a |
| F29 | Doctor-question feature | Question triage (category medicine/food/symptom/visit/admin/other, priority normal/high/urgent; EN/TE/HI keywords); cited doctor-facing research brief and safe suggested reply (the system never answers medical questions itself); routing, background research task, live doctor notification (SSE), threaded reply on the same channel (replies exempt from the 3/day cap; bypass quiet hours only when urgent); patient status waiting/answered/closed (research never exposed to patients); doctor email notifier (dry-run by default; send needs explicit owner confirmation; throttle 1 per patient per 10 min, urgent up to 3/hour); doctor and patient UI (question cards, research panel with citation chips, editable reply, toast and badge) | `cm/`, `web/src/` | 88 unit and 7 integration tests; live DeepSeek flash verified on demo patients; full loop verified live on 25 Oct: Telegram question, research, doctor reply in the console, threaded delivery to Telegram (commits 29cdeef, fbafdde, 81d56eb, 8d516bb, b3ffa90) | done (bug found and fixed live: the dev sender used the real clock while the API schedules by the demo clock, a day ahead, so the reply waited in the outbox) | Functionality, UI/UX, Technical depth | n/a |
| | **Total tied to slices F01-F16** | | | | | | **63** |

Slices since F29 are listed after this table. Points for F17-F29 were not re-estimated (shown as n/a); the 63 covers F01-F16. Not done: Google Cloud deployment (planned for 2026-10-25, NOT happened; see [docs/deploy/DEPLOY_PLAN.md](docs/deploy/DEPLOY_PLAN.md)), live Google verification of Gmail and Calendar, cassette replay (stubs), risk training (deferred). See (c) and (e).

### Slices since F29 (25 Oct 2026)

| Slice | What | Status |
|---|---|---|
| P1 | **Document upload (core)**: Safe upload of patient documents: type, size and content checks, quarantine until reviewed, never shown to the patient as advice | done |
| P2 | **Document extraction**: Text and field extraction from uploads into a draft for the doctor; nothing enters the record without approval | done |
| P3 | **Document doctor review**: Doctor review queue: approve, edit or reject an extracted document before it becomes memory | done |
| P4 | **Document intake channels**: Telegram and Gmail attachment intake into the same safe upload path | partial (Telegram done; the Gmail inbound loop is not wired) |
| P5 | **Patient own-data answers**: Instant answers about the patient's own recorded data (medicines taken, next visit, last result), website only; no medical advice, no drug or disease names in patient-facing text | done |
| P6 | **Demo accounts**: Two demo accounts only: demo.pt0906 (6-day) and demo.pt0960 (60-day) | done |
| P7 | **Firebase deploy plan**: Firebase Hosting for the doctor and patient UIs and Firebase Auth for login; plan in [docs/deploy/FIREBASE_PLAN.md](docs/deploy/FIREBASE_PLAN.md) | planned (cloud not deployed yet) |
| P8 | **UI audit and Fable review fixes**: Fixes from the UI audit and from the Fable code review | done |
| P9 | **AI evals batch 2**: Second batch of AI eval cases; see [docs/design/AI_EVAL_REPORT.md](docs/design/AI_EVAL_REPORT.md) | done |
| P10 | **Upload edge tests**: Edge-case tests for the upload path (bad types, oversize, empty, duplicate, hostile names) | done |

## (b) Git commit plan: one commit per slice

F01 to F16 below were committed as planned. F17 to F29 map to the newest commits, which are local (not pushed); they are listed in the table after the F16 block.

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

#### F17 to F29: actual local commits (git log, 25 Oct 2026)

| Slice | Commit | Message |
|---|---|---|
| F17 | 3836d3b | feat(rules): add R1-R6 reconciler with household screening and red-team tests |
| F18 | 909dddd | feat(memory): add memory engine v1 features, detectors, belief lifecycle and risk interval |
| F18 | 5b073e6 | feat(memory): wire nightly memory pipeline, conflicts and persistence |
| F19 | 55d29d3 | feat(ai): add AI eval suite, narrator and Ask-box guards, shared banned-term lexicon |
| F20 | 82bd17f | fix: close edge-case and invariant bugs with property, concurrency and contract tests |
| F21 | 650152a | feat(vision): add DeepSeek document extraction drafts for doctor review |
| F22 | d7aafb1 | feat(gmail): add real Gmail and Calendar adapter with push verification, tested offline |
| F23 | f89639f | docs(design): add RAG strategy v2 for patient memory retrieval |
| F23 | e625106 | feat(rag): add patient memory RAG with hybrid search, citations and live eval |
| F24 | 9d1bedd | feat(web): citation chips, patient-page Ask and honest live-mode patient app |
| F25 | 8db6687 | feat(demo): add deterministic 3-day, 30-day and 60-day demo accounts |
| F26 | a46c2f3 | build(deploy): production image, Cloud Tasks mode, task auth and deploy scripts (local only) |
| F27 | c9ad3fd | feat(telegram): route patient free text to the doctor queue with a template acknowledgement and urgent escalation |
| F28 | cf62004 | test(gmail): simulate 55 email scenarios end to end and fix HTML replies, token burn and Red approval by email |
| F29 | 29cdeef | feat(ai): triage patient questions and prepare a cited doctor brief with a safe suggested reply |
| F29 | fbafdde | feat(email): add doctor notification email for patient questions (dry-run by default, send needs explicit confirmation) |
| F29 | 81d56eb | feat(telegram): route patient questions to the doctor with research, live notification and threaded replies |
| F29 | 8d516bb | feat(web): doctor question cards with research brief, live notification and patient waiting status |
| F29 | b3ffa90 | fix(telegram): make the dev sender follow the demo clock so replies scheduled by the API are delivered |

Other commits in the same range, not given their own slice: 566fbcd docs: record live Telegram channel test; relax event-count invariant for superseded events; c130943 test: pin live research and email send off in the test environment; d122a79 docs(openspec): sync doctor-console and patient-app specs; 0614c46 chore: add helper to collect demo logins into a git-ignored env file; relax outbox test isolation; 9037042 and 148dccc chore: ignore Gmail token files and the gmail_cred folder; f3a9663 feat(ai): finish AI runtime live run, budget alerts and run notes (F15); bfe8f7a fix(web): live-mode defects (undo, request volume, raw strings, logged-out 401s, channel status); c3ca863 fix(api): admin usage merge, channel status route, nightly trigger, next-step and audit fixes, safer Telegram tests; d2b472c chore: harden .gitignore for cloud credentials, tokens and key files; 3c2992c chore: sync remaining specs, fixtures and docs.

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
| P0 | Deploy to Google Cloud (Cloud Run, asia-south1, one domain with several hostnames): planned for 2026-10-25, NOT done. Plan: [docs/deploy/DEPLOY_PLAN.md](docs/deploy/DEPLOY_PLAN.md) | I | Viability and deployment readiness |
| P0 | Rehearse the core loop on the real stack: patient request, doctor approves, patient sees "doctor approved"; Telegram tap to Red draft | all | Working demo |
| P1 | Verify the real Gmail inbound and Pub/Sub push path and Calendar against real Google (55 simulated scenarios with fakes; one real test email sent and received) | M | Second channel |
| P1 | Exercise the live Telegram Telugu and `/stop` paths; record a backup video (free text, rate limit, urgent text and the question loop were verified live on 25 Oct) | F | Integration evidence |
| P2 | Native-speaker review of Telugu templates and answers (answer text is mostly English); Hindi | K | Usability |
| P2 | Trained risk model deferred (ECE 0.22 at day 60) | C | Honest risk numbers |
| P2 | Per-clinic scoping of doctor reads: not built (district-wide today) | G | Privacy |
| P3 | Cassette replay for an offline demo (stubs today) | J | Offline backup |

Done since the last tracker: F27 Telegram free text, F29 doctor-question feature, F28 Gmail simulation (partial), AI runtime, memory engine v1, rules R1-R6, simulator and Day 3 / 30 / 60 evaluation, the TypeScript build error (build now passes).

## (d) One-line progress

23 of 29 feature slices done, 6 partial, 0 in progress, 0 planned, plus the post-F29 slices below (25 Oct 2026). Backend 1967 passed, 2 skipped, 3 xfailed (expected failures, known gaps); web typecheck OK, 241 tests pass, build OK; the doctor gate is enforced by a database constraint. Deployment to Google Cloud is planned for 2026-10-25 and has NOT happened.

## (e) Verified results (as of 2026-10-25 about 02:30 IST)

- Backend: 1967 passed, 2 skipped, 3 xfailed (expected failures, known gaps). Web: typecheck OK, 241 tests pass, build OK. AI eval suite: 97 offline cases.
- RAG live eval, 66 questions across day 3, 30 and 60 on PT-0142 (DeepSeek flash, mock data): abstain accuracy 98.5%, groundedness 96.4%, judge pass 95.5%, 0 temporal leakage, citation validity 1.0; retrieval recall@10 1.0 / 1.0 / 0.97 at days 3 / 30 / 60. Caveats: 3 model-side misses; the database-backend check disagrees with the in-memory harness within 0.106 on abstain accuracy because of rendering differences.
- Simulator Day 3 to 30 to 60: AUROC 0.645, 0.703, 0.796; Brier 0.261, 0.249, 0.197. ECE at day 60 is poor (0.22). The risk model uses fixed documented weights (not trained; training deferred, no fine-tuning planned, RAG is the memory layer).

## (f) Known limitations

- Doctors can read all clinics' patients (district-wide by design; per-clinic scoping not built).
- Append-only erase bypass via `SET LOCAL cm.allow_erasure`.
- Risk calibration: ECE 0.22 at day 60.
- Telugu answer text is mostly English; Telugu templates need native-speaker review.
- The simulator clock is one day ahead of the real date in the seeded data.
- Gmail live inbound and push path, Calendar and Cloud deployment are not yet verified against real Google; Cloud deployment (planned for 2026-10-25) has not happened.
- Live Telegram Telugu and `/stop` paths have not been exercised live (offline tests only).
- Doctor email notifier is dry-run by default; send mode needs explicit owner confirmation.
- The system never answers patient medical questions itself; the research brief is doctor-facing only.
- DOC-IMG-TYPE: image type checking on uploads is a known gap (expected failure).
- Doctors can see all clinics' patients (district-wide by design).
- Risk calibration is poor: ECE 0.22 at day 60.
- The Gmail inbound loop is not wired.
- Cloud is not deployed yet (Firebase plan only).
- DeepSeek and OpenAI are used on mock data only (`CM_DATA_CLASS=mock`; DeepSeek refused for real data). No real patient data.

## (g) Team

Manobiram (product owner, architecture, integration) · Idris (team member) · Abhishek (team member). Roles for Idris and Abhishek are to be confirmed.
