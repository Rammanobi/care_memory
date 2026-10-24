# CareMemory: agent conventions (read fully before coding)

FIRST read `MEMORY.md` (owner's standing instructions; do not edit it). It holds Rule 1: automatically log every feature add, feature removal, behaviour change and bug fix in OpenSpec (propose, implement, validate, archive) without being asked.

Authority order: coordinator rulings, then `../INTEGRATION_DECISIONS.md`, then `../CAREMEMORY_ARCHITECTURE.md`, then the feature specs in `../feature_specs/`. A spec sentence that contradicts INTEGRATION_DECISIONS is void.

## Rulings that override older text
- The task table is `task_runs` (PK `task_id`, `attempt`, `heartbeat_at`), never `jobs`. Cloud Run Jobs and the `cm-jobs` service account keep their names.
- Use `approval_id`, never `review_id`. Use `recorded_at`, never `received_at`.
- Code lives under `cm/`. There is no `/v1` API prefix.
- Runtime models are OpenAI or DeepSeek only, via `init_chat_model`. No Claude or Gemini at runtime. "Haiku" in old diagrams means `WORKER_MODEL`.
- Household contact screening (R6) is P0.
- JWT secret is `JWT_SIGNING_KEY` (HS256). Passwords use `hashlib.scrypt`.
- Docs bucket is `$PROJECT-cm-docs`. Queues: `agent-runs`, `resumes` (2/s, 4 concurrent, 6 attempts) and `outbound` (5/s, 10 concurrent).
- `dashboard_qa` runs inline in `cm-api`; red escalation is a `cm-sweeper` duty.

## Non-negotiables
1. Contracts in `cm/contracts/` are FROZEN at git tag `contracts-v1` (tier 2 at `contracts-v1.1`). Never edit them. Need a change? Append an RFC to `contracts/CHANGES.md` and stop that sub-task; Opus answers within 30 min.
2. Edit ONLY your lane's directories (table below). No edits outside your lane. `scripts/check_ownership.py` with `scripts/lanes.yaml` enforces it.
3. LLMs never compute stored numbers. Beliefs, risk, trust and conflicts come from `cm/memory` and `cm/rules` only.
4. No AI text leaves the system without a review decision or an approved template. Never bypass `cm/router`.
5. Never write "TB", "tuberculosis" or drug names in any patient or Supporter-facing string. Run `make banned-terms`.
6. No raw SQL outside `cm/store/` and `cm/memory/`. Agents use `cm/tools` only.
7. Every side effect is idempotent (idempotency key). LangGraph nodes re-run on resume. Outbox rows are written by the decision transaction.
8. Webhooks ack in under 1 s. No BackgroundTasks or threads after the response. Use `cm.core.tasks.enqueue(task_id=...)`; the Cloud Tasks name is the `task_id`. Task ids are colon-free.
9. All reads take `as_of`. Use `cm.store.as_of.query(pid, as_of)`. Never `datetime.now()`; use `cm.core.clock.now()`.
10. Never send real PII to an LLM: `cm.core.tokenize.tokenize()` on prompts; `assert_clean()` runs in `llm.py`.
11. Graph runs: always `durability="sync"`; side effects only inside `@task` with an idempotency key, or via the outbox; never wrap `interrupt()` in try/except; code before `interrupt()` is upsert-only.
12. Every external call goes through `cm.core.retry` (retry 429/5xx/timeouts, honour retry-after, never retry spend-cap or auth errors).
13. Long handlers heartbeat the `task_runs` row at least every 20 s and respect the SIGTERM flag (`cm.core.lifecycle.shutting_down`).
14. Doctor decisions go only through `cm/review/decide.py` (console, Gmail and sweeper alike).
15. Citation refs: E event, B belief, C conflict, R risk, G guideline chunk, D document chunk.
16. LLM providers: OpenAI or DeepSeek only. Get models via `cm.core.llm.get_model("ORCHESTRATOR"|"WORKER"|"VISION"|"EMBEDDING"|"JUDGE")`; never instantiate providers directly, never hardcode a model name or key. `deepseek:` is refused when `CM_DATA_CLASS=real`.
17. Keys live only in `.env` (git-ignored) or Secret Manager. Never in code, fixtures, logs, commits or chat. `.env.example` holds names and placeholders only.

## Lane ownership (INTEGRATION_DECISIONS §e: lane = exclusive directories)
| Lane | Exclusive dirs / files |
|---|---|
| L0 Contracts (Opus) | `cm/contracts/`, `fixtures/` goldens + `openapi.json`, `cm/store/migrations/versions/0001_core.py`, `contracts/CHANGES.md`, `scripts/check_ownership.py` + `scripts/lanes.yaml`, `cm/agents/prompts/`, `cm/agents/playbooks/`, `docs/maths.md`, `docs/generator.md` (repo-root `CLAUDE.md`, `Makefile`, `pyproject.toml` are scaffolded and then L0-owned) |
| A Data core | `cm/core/`, `cm/store/` (except `0001`, `0005`), migrations `0002`-`0004`, `cm/jobs/migrate.py` |
| B Sim + seed + console backend | `cm/sim/` (except `replay.py`, `cassette.py`, `sim_channels.py`), `cm/jobs/seed.py`, `cm/api/routers/{dashboard,admin,consent,templates}.py`, `cm/api/suppress.py`, migration `0005_views.py` |
| C Memory engine | `cm/memory/`, `models/` |
| D Rules + validator + identity | `cm/rules/`, `cm/validator/`, `cm/identity/`, `tests/redteam/` |
| E Runtime + gate + tools | `cm/agents/{orchestrator,runtime,gate,schema_guard}.py`, `cm/tools/{guard,registry,patient,detectors,review,messaging}.py`, `cm/jobs/sweeper.py` |
| N Narration + sub-agents | `cm/agents/subagents/`, `cm/tools/{dashboard,guidelines}.py` |
| F Telegram + Supporter + router | `cm/channels/{telegram,tg_*,binding,supporter_web,household,factory,webpush}.py`, `cm/router/` (except `degrade.py`; template YAML content is K's) |
| M Gmail + consent + calendar | `cm/channels/{gmail,gmail_parse,gmail_reply,calendar,consent_flows}.py`, `cm/router/degrade.py` |
| G Core API | `cm/api/` (except B's, J's and K's routers and `suppress.py`), `cm/review/` |
| H1 Doctor console | `web/` shell (`package.json`, `src/{main.tsx,router.tsx,api,auth,realtime,components,styles,mocks}`), `web/src/pages/{Login,ReviewQueue,Patients,Patient,Lens,Timeline}/` |
| H2 District + demo + admin | `web/src/pages/{District,Eval,Sim,Admin,Ask,Supporter}/`, `web/src/features/patient-tabs/` |
| I Infra + local + obs | `infra/`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `requirements*.txt`, `scripts/` (except L0's) |
| J Eval + replay + offline | `cm/eval/`, `cm/sim/{replay,cassette,sim_channels}.py`, `cm/jobs/eval_job.py`, `cm/api/routers/{sim,eval,channels}.py`, `tests/replay/` |
| K Content + mock feeds + RAG seed | `cm/router/templates/*.yaml`, `data/guidelines/`, `fixtures/text_bank.json`, `cm/channels/{chemist_csv,portal_mock}.py`, `cm/api/routers/mock_nikshay.py`, `cm/rag/`, `docs/{dpdp_notice_v1,breach_plan}.md` |
| Integration (Opus) | merges, `tests/integration/` |

## Build-time memory (OpenSpec)
OpenSpec is the build-time memory for agents (not the product's runtime memory). Workflow: `/opsx:propose "idea"` then `/opsx:apply` then `/opsx:archive`. Each lane records its changes under `openspec/changes/` (proposal, design, tasks); agreed behaviour lives in `openspec/specs/`. When to log, and the full propose/implement/validate/archive duty, is Rule 1 in `MEMORY.md`: follow it. Do not edit `openspec/`, `.claude/`, `package.json` or `package-lock.json` outside that workflow. Project context for agents is in `openspec/config.yaml`.

## Stack
Python 3.12 in the image (>= 3.11 supported), FastAPI, Pydantic v2 (strict), psycopg 3, LangChain v1, LangGraph 1.2.x, deepagents 0.7.30.
Before using any API marked with a warning sign in the architecture doc, run `python -c "import inspect, X; print(inspect.signature(X.f))"` and note the result in your lane's `NOTES.md`.

## Style
- `ruff format` + `ruff check`; type hints everywhere; functions up to 50 lines; pure functions in `memory/` and `rules/`.
- Tests: pytest, one test file per module, fixtures from `fixtures/*.json`. Mark network tests `@pytest.mark.live`.
- Logs: `cm.core.logging.get_logger()`; structured kwargs, never PII.
- Commits: `<lane>: <imperative summary>`; small and frequent.

## Definition of done
`make check` is green; your Protocol has a fake in `fakes.py`; fixtures are updated if output shapes changed (only through an RFC); a short `NOTES.md` is in your lane dir with verifications and open issues.

## When stuck more than 20 minutes
Write the blocker in your lane's `NOTES.md`, stub with the fixture, and move on. Do not redesign contracts.
