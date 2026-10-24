# CareMemory: integration decisions (final, input to the H0 contract freeze)

**Author:** lead architect (Opus), final integration pass, 23 Oct 2026.
**Inputs:** `CAREMEMORY_ARCHITECTURE.md`, `feature_specs/00`–`04`, `RAG_MEMORY_DESIGN.md`, `RELIABILITY_PLAYBOOK.md`, `TECH_RESEARCH_NOTES.md`, the addendum in `CAREMEMORY_STORY_AND_FEATURES.md`.

**Precedence, highest first:**
1. The coordinator rulings (§0).
2. This document.
3. `CAREMEMORY_ARCHITECTURE.md` (now edited to match this document).
4. Feature specs 01–04 and `RAG_MEMORY_DESIGN.md`.

A spec sentence that contradicts this document is void. Builders do not reopen anything decided here. New needs go through `contracts/CHANGES.md` (Opus answers within 30 min).

---

## 0. Rulings (already made, restated so nobody has to look elsewhere)

| # | Ruling |
|---|---|
| Z1 | The architecture doc's names win |
| Z2 | The task table is **`task_runs`** (PK `task_id`, with `attempt` and `heartbeat_at`). It is **not** `jobs`. Cloud Run Jobs and the `cm-jobs` service account keep their names. The repo module is `cm/store/task_runs_repo.py` |
| Z3 | Use **`approval_id`**, never `review_id` |
| Z4 | Use **`recorded_at`**, never `received_at` (this covers events, documents and chunks) |
| Z5 | Code lives under **`cm/`**. There is **no `/v1`** prefix |
| Z6 | Runtime models are **OpenAI or DeepSeek only**, via `init_chat_model`. There are no Claude or Gemini runtime providers. "Haiku" in old diagrams means `WORKER_MODEL` |
| Z7 | **Household contact screening is P0** |

---

## a. Contract change requests (RFCs): decisions

The source is in brackets: 01 = channels, 02 = AI core, 03 = dashboards, 04 = platform, RAG = `RAG_MEMORY_DESIGN.md`. For decisions: **A** = accept, **M** = modify, **R** = reject. "Owner" is the lane that writes the code (lanes are defined in §e).

### a1. Events (`cm/contracts/domain.py`, `Event` discriminated union on `type`)

| # | RFC | Dec. | Final name and shape | Owner |
|---|---|---|---|---|
| E1 | `CheckinPrompt` [01 R-1, 02] | **A** (P0) | `CheckinPrompt{outbox_id: UUID, channel: Literal["telegram","webpush","supporter_proxy"], for_date: date, sent_at: datetime}`. The outbox drainer appends one **after each successful send** of any check-in template (`checkin_daily`, `checkin_nudge`, the Supporter proxy prompt). `source="system"`, `reporter_mode="record"`, idempotency key `prompt:{outbox_id}`. R5, reply time and engagement drift all read it | F appends; C and D read |
| E2 | `RegimenChange` [02] | **A** (P0) | `RegimenChange{regimen_from: str \| None, regimen_to: str, line: Literal["first","second","other"], effective_date: date, prescriber_id: UUID \| None}`. The seed writes one at treatment start for every patient. R2 reads the latest one as of the lab result's `recorded_at`. A console "change regimen" action is P1 | B writes (seed); D reads (R2) |
| E3 | `ChannelUnreachable` [01 R-2] | **A** | `{channel: OutboundChannel, reason: Literal["blocked","gone","invalid_grant","other"], detail: str \| None}`. It degrades the channel profile. It **never** withdraws consent | F, M |
| E4 | `PortalRegistration` [01 R-3] | **A** | `{nikshay_id, notified_on: date, facility_code, treatment_start: date}`, key `nk:{nikshay_id}:reg` | K |
| E5 | `HouseholdContactEvent` [01 R-4] | **A** (P0) | `{contact_id: UUID, action: Literal["listed","screened","flagged","referred","doctor_decision","declined"], relation?, age_band?: Literal["<5","5-14","15-59","60+"], symptoms?: {cough_2w, fever, weight_loss, night_sweats}, contact_agreed?: bool, doctor_decision?: Literal["refer_test","tpt_decided","no_action"], note?}`. **Names never go in event payloads**; they live only in `household_contacts.enc_name`. Key `hh:{contact_id}:{action}:{client_uuid}` | F (capture), G (API) |
| E6 | `ConsentEvent` mirrored into `events` [01 F11] | **A** | The same `ConsentEvent` model is also a member of the `Event` union (timeline). `consents` stays the ledger the router and `as_of` read | M |
| E7 | `FreeTextNote` (in `ParsedInbound`, arch §3.2) | **R** | It was never in the union. Free text becomes `ContextNote{origin: "patient_text"\|"supporter_text"\|"doctor", kind: str, text_tokenised: str, needs_clarification: bool}` | N |
| E8 | `Detection` [02] | **M** | Internal model in `memory.py`, not an event | C |

### a2. Tables, columns and views

| # | RFC | Dec. | Final name and shape | Owner |
|---|---|---|---|---|
| T1 | `household_contacts` table + view [01 R-4, 03 D9] | **A** (P0) | `household_contacts(contact_id PK, patient_id FK, relation, age_band, enc_name bytea NULL, symptoms jsonb, flagged bool, screened_at, referred bool, doctor_decision, decided_by, created_at, updated_at)`. `enc_name` is encrypted under the **patient's** DEK, so the patient's erasure shreds it. The table is a **projection** of `HouseholdContactEvent` and can be rebuilt. The view is `v_contact_screening(district_id, block_id, as_of, contacts_listed, contacts_screened, contacts_referred, patients_overdue)` for patients past `contacts_due_day` (default 14). The flag rule is deterministic: `age_band == "<5" OR any(symptoms)` | DDL L0; repo A (`household_repo.py`); capture F; view B (0005) |
| T2 | New `approvals` columns [02, 03] | **M** | **Added:** `proposal_group_id uuid` (links re-drafts), `graph_kind text CHECK IN ('deep','lg')` (resume mapping), `due_at timestamptz` (**stored**, set at upsert: Red = created + 4 h, Amber = next 12:00 IST, Green = end of day), `sample_reason text NULL CHECK IN ('anomaly','random_10pct')`. **Rejected names:** `redraft_no` (use the existing `redraft_count`), `tool_call_id` (use `interrupt_id`; for deep-agent threads its value **is** the HITL tool-call id, and for the LangGraph review graph it is `gate:{proposal_group_id}:{redraft_count}`), `proposal` (use `payload`). `review_decisions.nonce` is rejected (the token lives in `approval_tokens`) | DDL L0; repo A |
| T3 | `settings` [03 §7] | **A** | `settings(key text PK, value jsonb NOT NULL, version int NOT NULL DEFAULT 1, updated_by uuid, updated_at timestamptz)`. Keys: `thresholds` (a `RuleThresholds` JSON) and `channels.{telegram\|gmail\|calendar\|wearable}.enabled` (bool). `supporter_web` is always on and has no key. Optimistic lock on `version`. The router, `cm-sweeper` and R6 read through `settings_repo` (60 s cache) | DDL L0; repo A; API B |
| T4 | `auth_credentials` [03 §8] | **A** | `auth_credentials(person_id PK FK persons, username UNIQUE, password_hash text, token_version int NOT NULL DEFAULT 1, active bool NOT NULL DEFAULT true, last_login_at)`. Hashes use **`hashlib.scrypt`** (no new dependency). `persons.token_version` is rejected | DDL L0; G |
| T5 | `erasure_requests` [03 §7] | **A** | `erasure_requests(request_id PK, person_id, reason, status CHECK IN ('awaiting_second_approval','approved','executing','done','rejected'), requested_by, requested_at, approved_by, approved_at, executed_at, error)`. A CHECK enforces `approved_by <> requested_by`. The executor is `cm.erase_person()` (A), run by `cm-nightly` step C | DDL L0; API B; procedure A |
| T6 | `cm.documents` / `cm.text_chunks` replace `guideline_chunks` [RAG §3, 04 0004] | **M** | **Accepted**, with these changes: (1) the column is **`recorded_at`**; (2) `guideline_chunks` becomes a **view** over `text_chunks WHERE doc_type='guideline' AND status='active'`; (3) `embedding halfvec(1536)` with a migration flag `RAG_VECTOR_TYPE=vector` if pgvector < 0.7; (4) the chunk citation ref is **`[G:chunk_id]`** for guidelines and **`[D:chunk_id]`** for patient documents. RAG's `[C:…]` is rejected because `C` means conflict. **Build scope ("RAG-lite"):** P0 = DDL + guideline seed. P1 = `search_guidelines` hybrid retrieval and patient prose chunks. The RAG doc's SQL tool (item 10) is rejected: P6/§3.13 ban SQL generation, and typed tools already exist | DDL A (0004); guideline seed K (`cm/rag/`); retrieval tool N (P1) |
| T7 | `channel_bindings` columns [01 R-6] | **A** | Add `meta jsonb` (web-push keys), `status CHECK IN ('pending','active','blocked','revoked')`, `invite_expires_at`. Add channel value `webpush` | L0 |
| T8 | `gmail_state.last_push_at` [01 R-7] | **A** | Column only. The 30-minute sweep stays as it is | L0 / M |
| T9 | `audit_log.result_ids text[]` [02] | **A** | Needed for the investigator's post-hoc citation check | L0 / E |
| T10 | `task_runs` extra columns [03, 04] | **A** | Add `error_class text` (`retryable\|spend_cap\|auth\|invalid\|unknown`), `progress real`, `step text`. The status column is named **`state`** (03's `status` is rejected) | L0 / A |
| T11 | `identity_vault.phone_hmac`, `nikshay_hmac` [03] | **A** | Columns at H0. Blind-index search is P1 | L0 / A |
| T12 | `persons.backup_for` [03] | **A** | The backup-doctor link for the sweeper ladder | L0 |
| T13 | `sim_clock` columns [03, 04] | **A** | Add `escalation_offset_hours real DEFAULT 0` (honoured only when `DEMO_MODE=1`), `max_computed_day int`, `status CHECK IN ('seeding','ready')` | L0 / A |
| T14 | `eval_runs` cache key [04] | **A** | Add `gen_version, engine_version, model_version, status CHECK IN ('running','done','failed'), task_id, finished_at`, with UNIQUE `(seed, gen_version, engine_version, model_version)` | L0 / J |
| T15 | `sim_inbox` [04 F3] | **A** | `sim_inbox(id bigserial, persona, channel, direction CHECK IN ('in','out'), body, buttons jsonb, created_at)`. Offline mode only | L0 / J |
| T16 | `mock_nikshay_patients`, `mock_nikshay_payments` [01 F10] | **A** | Mock-only tables, filled by `cm-seed` | L0 / K |
| T17 | `uploads` bytea fallback [01 R-10] | **R** | Use the bucket (I4) | — |
| T18 | `card_citations.ref_type` | **M** | `ref_type ∈ {E, B, C, R, G, D}`. `ref_id` becomes **text**, so risk refs `R:{patient_token}@{day}` fit | L0 |
| T19 | Views [03 §1, §4] | **M** | **P0:** extend `v_district_daily` (high risk, Red over 4 h, contacts, 7-day deltas), add `v_payments_stuck` and `v_contact_screening`. **P1:** `v_cascade`, `v_pharmacy_activity`. **Rejected:** `v_review_queue` (`due_at` and `sample_reason` are now stored columns, so `approvals_repo.queue()` does the join) | B (0005) |
| T20 | `cm.notify_live()` triggers [03 §0.5] | **A** | On `approvals`, `review_decisions`, `task_runs`, `outbox`, `sim_clock`, `eval_runs`, `settings`. The payload carries **ids only** | DDL B (0005), to G's spec |

### a3. Approvals: kinds and the shared decision service

| # | RFC | Dec. | Final |
|---|---|---|---|
| K1 | New approval kinds [01 R-5] | **M** | Final `ReviewKind` = `card, brief, visit_list, conflict, identity, digest, needs_human, lab_confirm, contact_review, district_report`. `lab_confirm` and `district_report` have P1 producers. A CSV header mapping, "channel failed" and "household declined" are `needs_human` with `payload.subkind`. A Red system alert is kind `conflict`, tier `red` |
| K2 | Shared `review_service.decide()` [01, 03] | **A** (P0) | Module **`cm/review/decide.py`**, owned by **lane G**. Signature: `decide(approval_id: UUID, d: ReviewDecisionIn \| ExpiredDecision, *, via: Literal["console","gmail","sweeper"], actor_id: UUID \| None) -> ReviewDecisionOut`. The console route, the Gmail reply path (M) and the sweeper's `expired` (E) all call it. **One transaction:** `SELECT … FOR UPDATE` (409 `already_decided` when not pending) → validate (reject on Red or Amber needs a `reason`; banned terms in Supporter- or patient-facing text return 422; doctor-audience number mismatches become `warnings`) → insert `review_decisions` → update `approvals.status` → append `ReviewDecisionEvent` (key `decision:{approval_id}`) → **insert `outbox` rows** for approve/edit of a send artefact (`dedup_key` rule in §f C23) → `edit_examples` on edit → `task_runs` row `resume-{approval_id}` (ON CONFLICT DO NOTHING) → `audit_log`. **After commit:** enqueue `resume-{approval_id}` on `resumes` and `drain-{channel}-{epoch_min}` on `outbound`. Red cannot be decided `via="gmail"` |
| K3 | Who writes outbox rows on approval [02 F8 vs arch §3.10] | **M** | **The decision service writes them** (arch rule: same transaction as the decision). On resume, the gated tool body (`send_message`, `publish_card`, `submit_for_review`) does **not** send. It upserts the same `dedup_key` (a no-op) and returns `"queued:{outbox_id}"`. The recipients come from `ProposalOut.recipients`, so every send proposal must carry them |
| K4 | `BulkDecisionIn{review_ids}` [02] | **R** | `BulkDecisionIn{approval_ids, action: "approve", viewed_approval_ids}`. Red is always refused (`red_not_bulk`). Amber items must appear in `viewed_approval_ids` (`amber_not_viewed`) |
| K5 | Decisions vocabulary | **A** | Public `ReviewDecisionIn.action ∈ {approve, edit, reject}`. Internal `DecisionAction` adds `expired` (sweeper only). `ReviewDecisionIn.evidence_viewed: bool` is accepted for audit only |

### a4. Memory, rules and evaluation contracts

| # | RFC | Dec. | Final |
|---|---|---|---|
| M1 | Pure `run_in_memory` [04 F2 D1] | **A** (P0) | `cm.memory.pipeline.run_in_memory(events: pd.DataFrame, consents: pd.DataFrame, as_of_days: list[int], *, exclude_sources: Sequence[str] = ()) -> InMemoryResult`. `InMemoryResult` is a frozen dataclass of two DataFrames. `.risk` has columns `[patient_token, day, p_miss7, miss7_ci_low, miss7_ci_high, p_dropout14, ci_low, ci_high]`; `.beliefs` has `[patient_token, day, belief_id, kind, subject, state, posterior, ci_low, ci_high, confirmed_at, retired_at]`. **It takes no truth parameter**, and a test checks the signature. `cm-nightly` and `snapshot()` call the **same** per-patient functions, so there is one engine and two drivers |
| M2 | Pure `filter_as_of` [04 F2] | **A** | `cm.store.as_of.filter_as_of(events_df, as_of_day, consents_df) -> DataFrame`: `occurred_at ≤ T AND recorded_at ≤ T`, latest non-superseded, with withdrawn-now sources dropped. `query(pid, as_of)` uses the same predicate in SQL. A property test checks they agree (owner A) |
| M3 | DataFrame `reconcile` [04 D2] | **A** (P0) | `cm.rules.reconcile.reconcile_frame(events: pd.DataFrame, patient: PatientRow, as_of: date, thresholds: RuleThresholds) -> list[Conflict]`. `reconcile(pid, as_of)` = load + `reconcile_frame`. `fast_path(event)` runs R2/R4 only. There is one implementation |
| M4 | Second risk head `p_miss7` [04 F2] | **A** | `models/risk_v1.joblib` holds two calibrated logistic heads: `dropout14` (the displayed `RiskScore.p`, arch §3.7 target) and `miss7`. Add `RiskScore.p_miss7`, `miss7_ci_low`, `miss7_ci_high` (nullable). `risk_scores` gets the same three columns |
| M5 | Label definitions [04 F2] | **A** (frozen) | **`miss7` = 1 if there are ≥ 2 true misses (forced misses included) in days d+1..d+7. `dropout14` = 1 if a run of ≥ 7 consecutive true misses lies inside d+1..d+14.** These go in `docs/maths.md` at H0 and feed `frozen_spec_hash`. Seeds: train 1000–1099, calibrate 1100–1149, evaluate ≥ 2000. Demo seed 42 is allowed but flagged `demo_cohort`. Precomputed: 2042, 2077, 2026 |
| M6 | `EvalReport` shape [03 §6 vs 04 F2] | **M** | **04's nested shape wins**, typed in `evalsim.py` (§d). 03's flat fields (`auroc_miss7`, `caught`, …) are rejected. The UI reads `curves.miss7[i].model.auroc` and `facts.totals`. `facts.totals: PatternScore` (the sum over patterns) is **added** so the scorecard tiles need no client maths. Also added: `safety: SafetyCounters` (03) and `excluded: list[str]` and `degraded: bool` (04) |
| M7 | `snapshot(…, exclude_sources)` what-if [03 §3] | **A** (P1) | `cm.memory.snapshot.snapshot(pid, day, exclude_sources=())` calls `run_in_memory` for one patient. It returns `computed="what_if"`. It is first on the cut list (§g) |
| M8 | R6 contacts-unscreened rule [01 F13, 03, addendum] | **A** (P0) | Rule id **`R6`** (03's `R6_contacts` and 01's `R6_contacts_unscreened` are rejected as ids; the label is "Contacts not screened"). **Logic:** from treatment day `contacts_due_day` (default 14), fire if the patient has **zero** listed contacts, **or** any listed contact has `screened_at IS NULL`. **Suppressed** when a `ContextNote{kind:"household_declined"}` exists. Tier Amber. Evidence: the treatment-start `RegimenChange`/registration event plus the contact events. It closes when all listed contacts are screened. When an R6 conflict **opens**, the deterministic review graph (`cm/agents/gate.py`) creates one `approvals(kind=conflict, tier=amber)` with system text, deduped on `conflict_id`. This satisfies the addendum's "raises an amber review item". No LLM, no TPT wording. `FlagChip.rule` gains `"R6"` |
| M9 | 02 schemas `NarrationRequest`, `JudgeVerdict`, `NightlyReport`, `TokenMap`, `InjectionScan`, `Detection` | **A** | Internal models (§d) |
| M10 | Store semantic-index field | **M** | One `PostgresStore` index config, `fields: ["text"]`. Edit examples are stored as `{"text": before, "after": …, "kind": …}` (02's `["before"]` is rejected) |
| M11 | `ProposalOut` / `EvidenceItem` shape of `approvals.payload` / `evidence` [03] | **A** | Typed in `review.py`. `ProposalOut` gains `recipients: list[Recipient{person_id, token, channel}]` (needed by K3) |

### a5. Endpoints, realtime and auth

| # | RFC | Dec. | Final |
|---|---|---|---|
| P1 | `/sim/*` [03 §6, 04 F3] | **M** | **P0:** `POST /sim/reset?seed&patients&days` (no params = restore demo seed 42; 03's `/sim/reset-demo` is rejected), `POST /sim/advance?to_day&mode=fast\|full`, `GET /sim/clock`, `POST /sim/escalation-offset` and `POST /sim/sweep-now` (both `DEMO_MODE=1` only, else 404), `GET /sim/inbox?persona&after` and `POST /sim/inbox/{persona}/reply` (both `CM_OFFLINE=1` only). **P1:** `POST /sim/inject`. `mode=fast` moves the clock only (projections are precomputed). `mode=full` runs that day's schedule; on GCP the nightly part runs as a `cm-nightly` execution with `--as-of` overrides (202 + `task_id`), because a 40-patient nightly does not fit `cm-api`'s 60 s timeout. Going backwards returns 409. The console play loop runs at `SIM_PLAY_INTERVAL_MS=400` in fast mode |
| P2 | `GET /eval/runs/{run_id}` [04] | **A** | `GET /eval?seed` → 200 `EvalReport` when cached or computed within 45 s. Otherwise **202 + `Location: /eval/runs/{run_id}`** (03's `/task-runs/{id}` for eval is rejected). The judge **re-roll is `GET /eval?seed=S` in memory** (about 20 s, 200 patients). It does **not** call `/sim/reset` (03's re-roll flow is rejected). Seeds < 2000 other than 42 return 422. `GET /task-runs/{task_id}` is kept for seed and nightly progress |
| P3 | SSE `GET /stream?topics=` [03 §0.5] | **A** (P0, cuttable) | As specified: one dedicated LISTEN connection per `cm-api` instance (outside the pool; +4 connections at the 4-instance cap), a 10-minute ring buffer, rotation at 50 s, `Last-Event-ID` replay, role/scope filter, `LiveEvent` payload. The fallback is polling (15 s for the queue). `cm-api` timeout stays at 60 s. Cut #9 drops SSE and keeps 5 s polling |
| P4 | JWT auth [03 §8, 04 F6] | **A** | HS256 (PyJWT). Secret **`JWT_SIGNING_KEY`** (03's `JWT_SECRET` is rejected). Claims `{sub, role, person_id, clinic_id, district_id, tv, iat, exp, jti}`. TTL 480 min. Sent as the `cm_session` cookie (HttpOnly, Secure, SameSite=Strict) **and** accepted as `Authorization: Bearer`. Cookie mutations require `X-CM-Client: web`. `tv` is checked against `auth_credentials.token_version` (60 s cache). Login is limited to 10/min per IP and 5/min per username. Roles: `doctor, supporter, sts, dto, admin, chemist, lab`, plus `patient` (PWA magic link only, P1). Endpoints: `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`, and `POST /auth/demo-switch` (P1, `DEMO_MODE`) |
| P5 | `/review/queue` envelope [03] | **A** | Response is `ReviewQueueOut{counts, items, next_cursor, server_time, sim_day}`, not a bare list |
| P6 | 01 R-8 endpoints | **M** | **P0:** `POST /ingest/household-contact`, `GET /patients/{pid}/household` (returns `HouseholdSummary`, with names decrypted only for the treating doctor and the assigned Supporter), `GET /patients/{pid}/channel-profile`, `/mock/nikshay/*`, worker `/tasks/checkin-nudge`, `/tasks/portal-sync`, `/tasks/calendar-sync` (P0 only for the F13 `family_screen` kind). **P1:** `POST /ingest/lab-report`, `/pwa/*`, `/tasks/district-report`, `POST /identity/resolve` and `GET /identity/unmatched` (admin) |
| P7 | 03 §10.2 endpoints | **M** | **P0:** `GET /patients/{pid}`, `/patients/{pid}/series`, `/patients/{pid}/belief-pins`, `GET /beliefs/{id}`, `GET /conflicts/{id}`, `/dashboard/district/{id}/payments-stuck`, `GET /task-runs/{task_id}`, `GET/POST /channels[/{channel}]` (cuttable, #2), `GET/POST/PATCH /admin/persons`, `POST /templates`, `POST /templates/{id}/retire`, `GET /templates/{id}/preview`, `GET/PUT /admin/settings` (read P0; the thresholds editor UI is P1), `GET /erasure-requests`, `POST /erasure-requests/{id}/approve`. **P1:** `GET /review/metrics`, district `cascade`, `pharmacies`, `supporters`, `report`, `reveal`, `GET /query/suggestions`, `GET /admin/audit`, and the `exclude_sources` parameter |
| P8 | `POST /query` mode [03 §5 vs arch §3.1] | **M** | `dashboard_qa` runs **inline in `cm-api`** (no side effects, user waiting, 25 s budget). The `dashboard_question` task type is **removed** from the orchestrator. The whole feature is P1 |
| P9 | `/tasks/escalate` [02 F6 diagram] | **R** | Red escalation is a `cm-sweeper` duty |

### a6. Infrastructure

| # | RFC | Dec. | Final | Owner |
|---|---|---|---|---|
| I1 | Secret `DB_PASSWORD_ADMIN` [04] | **A** | `cm-jobs` only (migrations, erasure) | I |
| I2 | `iam.serviceAccountUser` on `cm-tasks-invoker` [04] | **A** | For `cm-api`, `cm-worker` and `cm-jobs` (all three enqueue OIDC tasks) | I |
| I3 | `roles/run.developer` for `cm-api` [04] | **M** | On `cm-seed` and `cm-eval` (as 04), **plus** `cm-nightly` (`/sim/advance mode=full`) and `cm-sweeper` (`/sim/sweep-now`), because executions with overrides need `run.jobs.runWithOverrides` ⚠ | I |
| I4 | GCS bucket [01 R-10, 04, RAG] | **M** | One bucket, **`$PROJECT-cm-docs`** (`caremem-hack-cm-docs`), in asia-south1, with uniform access and public-access prevention. Prefixes: `uploads/lab/`, `uploads/csv/`, `raw/`, `guidelines/`. A 30-day lifecycle rule applies to `uploads/`. `roles/storage.objectAdmin` on the bucket for `cm-api`, `cm-worker` and `cm-jobs`. 01's `caremem-uploads` is rejected | I |
| I5 | `cm-migrate` job [04] | **A** | 600 s timeout, run by Cloud Build before each deploy. It runs alembic, `PostgresSaver.setup()`, `PostgresStore.setup()` (schema `lg`), the pgvector ≥ 0.7 assert and the grants | I (script), A (migrate.py) |
| I6 | `--edition=ENTERPRISE` on Postgres 16 [04] | **A** | PG16 defaults to ENTERPRISE_PLUS, which rejects `db-custom-1-3840` | I |
| I7 | `run.invoker` for `cm-tasks-invoker` on `cm-nightly` and `cm-sweeper` [04] | **A** | Scheduler `jobs:run` | I |
| I8 | Scheduler additions [01] | **A** | 18:30 evening check-ins and 19:00 Supporter proxy (both `/tasks/checkins` with `{slot}`), and 00:30 `/tasks/portal-sync`. P1: calendar sync after nightly, monthly district report | I |
| I9 | `DEMO_MODE` env flag [03] | **A** | It gates the escalation offset, sweep-now, demo-switch and the `/demo` page | A (config), I (env) |
| I10 | VAPID secrets [01 F2] | **A** (P1) | `VAPID_PRIVATE_KEY` in Secret Manager. Only needed if F2 is built | I |
| I11 | Queue rates | **M** | `agent-runs`/`resumes`: 2/s, 4 concurrent, 6 attempts (the old "3/s, 5 concurrent" in the arch diagram and in 02 is void). `outbound`: 5/s, 10 concurrent | I |

---

## b. Final table list (schema `cm`; LangGraph tables live in schema `lg`)

`0001_core` (Opus, H0) creates **every** table below except the RAG pair (`0004_rag`, lane A). The DDL is the contract.

| Group | Table | Key columns (PK first) |
|---|---|---|
| Org | `districts`, `blocks`, `clinics` | `district_id`, `name`; `block_id`, `district_id`, `name` (neutral "Block A–E"); `clinic_id`, `block_id`, `name` |
| Identity | `persons` | `person_id`, `role`, `token` UNIQUE (`P-0042`, `S-07`, `D-02`, `C-03`), `clinic_id`, `district_id`, `backup_for` |
| | `identity_vault` | `person_id`, `enc_name`, `enc_phone`, `enc_email`, `dek_wrapped`, `lang`, `phone_hmac`, `nikshay_hmac` |
| | `auth_credentials` | `person_id`, `username` UNIQUE, `password_hash`, `token_version`, `active`, `last_login_at` |
| | `patients` | `patient_id`, `person_id`, `clinic_id`, `treatment_start`, `regimen`, `phase`, `status`, `channel_profile jsonb`, `nikshay_id` |
| | `support_assignments` | `patient_id`, `supporter_id`, `from_date`, `to_date` |
| | `channel_bindings` | `person_id`, `channel` (telegram/gmail/web/webpush), `external_id`, `bound_at`, `invite_code`, `invite_expires_at`, `status`, `meta jsonb` |
| | `consents` | `consent_id`, `person_id`, `source`, `purpose`, `state`, `effective_at`, `via`, `notice_version` (append-only) |
| L0 | `events` | `event_id`, `patient_id`, `type`, `occurred_at`, `recorded_at`, `source`, `reporter_id`, `reporter_mode`, `channel`, `consent_id`, `payload`, `supersedes`, `idempotency_key` UNIQUE, `sim_run_id` (INSERT-only trigger) |
| L1–L3 | `features_daily` | (`patient_id`, `as_of`), `features`, `computed_at`, `engine_version` |
| | `beliefs` | `belief_id` + `as_of`, `patient_id`, `kind`, `subject`, `state`, `posterior`, `ci_low`, `ci_high`, `n_instances`, `first_seen`, `confirmed_at`, `retired_at`, `retired_reason` |
| | `belief_evidence` | `belief_id`, `event_id`, `role` |
| | `hypothesis_requests` | `id`, `patient_id`, `proposed_by`, `kind`, `params`, `status`, `result_belief_id` |
| | `conflicts` | `conflict_id`, `patient_id`, `rule` (R1–R6), `tier`, `evidence_ids`, `opened_as_of`, `closed_as_of` |
| | `risk_scores` | (`patient_id`, `as_of`), `p`, `ci_low`, `ci_high`, `p_miss7`, `miss7_ci_low`, `miss7_ci_high`, `drivers`, `model_version` |
| | `memory_cards` | `card_id`, `patient_id`, `as_of`, `audience`, `body`, `sentences`, `cut_ratio`, `fallback_used`, `status`, `approval_id` |
| | `card_citations` | `card_id`, `sentence_idx`, `ref_type` (E/B/C/R/G/D), `ref_id text` |
| | `household_contacts` | `contact_id`, `patient_id`, `relation`, `age_band`, `enc_name`, `symptoms`, `flagged`, `screened_at`, `referred`, `doctor_decision`, `decided_by`, `created_at`, `updated_at` |
| Review | `approvals` | `approval_id`, `patient_id`, `thread_id`, `interrupt_id`, `task_id`, `proposal_group_id`, `graph_kind`, `tier`, `kind`, `payload`, `evidence`, `status`, `redraft_count`, `sample_reason`, `created_at`, `due_at`, `expires_at`, `reminded_at`, `escalated_at`; UNIQUE (`thread_id`, `interrupt_id`) |
| | `review_decisions` | `decision_id`, `approval_id` UNIQUE, `doctor_id`, `action`, `edited`, `reason`, `via`, `decided_at` |
| | `approval_tokens` | `token_hash`, `approval_id`, `doctor_id`, `expires_at`, `used_at` |
| | `edit_examples` | `example_id`, `decision_id`, `doctor_id`, `kind`, `before`, `after` |
| | `templates` | `template_id`, `key`, `lang`, `body`, `slots`, `tier`, `status`, `approved_by`, `approved_at` |
| | `outbox` | `outbox_id`, `recipient_id`, `channel` (telegram/gmail/webpush/web_inbox/calendar), `body`, `decision_id`, `template_id`, `status`, `attempts`, `next_attempt_at`, `locked_by`, `locked_at`, `provider_message_id`, `sent_at`, `dedup_key` UNIQUE; CHECK (`decision_id` or `template_id`) + approved-template trigger |
| RAG | `documents` | `document_id`, `patient_token`, `doc_type`, `source`, `author_role`, `occurred_at`, `recorded_at`, `consent_id`, `language`, `confidence`, `extraction_model`, `content_hash` UNIQUE, `version`, `supersedes`, `sensitivity`, `retention_until`, `gcs_uri`, `status`, `extra` |
| | `text_chunks` | `chunk_id`, `document_id`, `parent_id`, `patient_token`, `doc_type`, `status`, `occurred_at`, `recorded_at`, `consent_id`, `language`, `sensitivity`, `content`, `content_hash`, `embedding halfvec(1536)`, `embedding_model`, `tsv` (generated), `extra` |
| Ops | `task_runs` | `task_id`, `task_type`, `thread_id`, `patient_id`, `state`, `attempt`, `heartbeat_at`, `worker_instance`, `error`, `error_class`, `progress`, `step`, `tokens_in`, `tokens_out`, `cost_usd`, `created_at`, `updated_at` |
| | `audit_log` | `id`, `at`, `actor`, `role`, `action`, `tool`, `args_hash`, `result_ids`, `patient_id`, `thread_id`, `ip` (INSERT-only) |
| | `gmail_state` | `mailbox`, `history_id`, `watch_expiration`, `last_sweep_at`, `last_push_at` |
| | `settings` | `key`, `value`, `version`, `updated_by`, `updated_at` |
| | `erasure_requests` | `request_id`, `person_id`, `reason`, `status`, `requested_by`, `requested_at`, `approved_by`, `approved_at`, `executed_at`, `error` |
| | `sim_clock` | `run_id`, `seed`, `sim_day`, `day0_date`, `max_computed_day`, `escalation_offset_hours`, `status` |
| | `eval_runs` | `run_id`, `seed`, `gen_version`, `engine_version`, `model_version`, `status`, `task_id`, `started_at`, `finished_at`, `report` |
| | `sim_inbox` | `id`, `persona`, `channel`, `direction`, `body`, `buttons`, `created_at` |
| Mock | `mock_nikshay_patients`, `mock_nikshay_payments` | `nikshay_id`, …; (`nikshay_id`, `month`), `amount`, `status`, `paid_on`, `pfms_ref` |
| Views | `guideline_chunks` (over `text_chunks`), `v_patient_summary`, `v_district_daily` (materialised), `v_review_sla`, `v_supporter_activity`, `v_payments_stuck`, `v_contact_screening`; P1: `v_cascade`, `v_pharmacy_activity` | readable by `cm_reader` |
| LangGraph | `lg.*` (from `PostgresSaver.setup()` / `PostgresStore.setup()`) | — |

**Migrations:**

| Migration | Owner | What it does |
|---|---|---|
| `0001_core` | L0 | All tables except RAG |
| `0002_reliability` | A | Outbox CHECK/trigger, claim indexes, `task_runs` indexes |
| `0003_security` | A | Roles, grants, INSERT-only triggers, `cm.erase_person()` |
| `0004_rag` | A | `documents`, `text_chunks`, HNSW/GIN indexes, `guideline_chunks` view |
| `0005_views` | B | All `v_*` views and the `notify_live` triggers |

---

## c. Final endpoint list (no prefix; P = priority; owner = lane that writes the route)

| Area | Method + path | P | Owner |
|---|---|---|---|
| Webhooks | `POST /webhooks/telegram`, `POST /webhooks/gmail` | P0 | G (route + verification); F / M (handlers) |
| Ingest | `POST /ingest/chemist-csv`, `/ingest/lab`, `/ingest/supporter`, `/ingest/household-contact`, `/ingest/portal` | P0 | G (parsers K / F) |
| | `POST /ingest/wearable`, `/ingest/lab-report` | P1 | G |
| Worker (OIDC) | `/tasks/run`, `/tasks/resume`, `/tasks/send`, `/tasks/drain-outbox`, `/tasks/checkins` (`{as_of, slot}`), `/tasks/checkin-nudge`, `/tasks/digest`, `/tasks/visit-lists`, `/tasks/gmail-fetch`, `/tasks/gmail-watch-renew`, `/tasks/gmail-sweep`, `/tasks/portal-sync`, `/tasks/calendar-sync` | P0 | G |
| | `/tasks/district-report` | P1 | G |
| Patients | `GET /patients`, `GET /patients/{pid}`, `/patients/{pid}/memory`, `/card`, `/lens`, `/funnel`, `/timeline`, `/series`, `/belief-pins`, `/household`, `/channel-profile`; `GET /events/{event_id}`, `/beliefs/{belief_id}`, `/conflicts/{conflict_id}` | P0 | G |
| | `exclude_sources` on `/memory` and `/funnel` | P1 | G |
| Agent | `POST /agent/tasks`, `GET /agent/tasks/{task_id}` | P1 (investigate) | G |
| Review | `GET /review/queue`, `GET /review/{approval_id}`, `POST /review/{approval_id}/decision`, `POST /review/bulk-decision` | P0 | G |
| | `GET /review/metrics` | P1 | G |
| Templates | `GET /templates`, `POST /templates`, `POST /templates/{id}/approve`, `POST /templates/{id}/retire`, `GET /templates/{id}/preview` | P0 | B |
| Consent | `GET /consents/{person_id}`, `POST /consents`, `POST /erasure-requests`, `GET /erasure-requests`, `POST /erasure-requests/{id}/approve` | P0 | B |
| Dashboards | `GET /dashboard/clinic/{clinic_id}/summary`; `GET /dashboard/district/{id}/summary`, `/blocks`, `/trends`, `/payments-stuck` | P0 | B |
| | district `/cascade`, `/pharmacies`, `/supporters`, `/report`; `POST …/reveal` | P1 | B |
| Supporter | `GET /supporter/{sid}/visit-list` | P0 | G |
| Q&A | `POST /query`, `GET /query/suggestions` | P1 | N (agent) + G (route) |
| Realtime | `GET /stream?topics=` | P0 (cuttable) | G |
| Sim | `POST /sim/reset`, `POST /sim/advance`, `GET /sim/clock`, `POST /sim/escalation-offset`, `POST /sim/sweep-now`, `GET /sim/inbox`, `POST /sim/inbox/{persona}/reply` | P0 | J |
| | `POST /sim/inject` | P1 | J |
| Eval / ops | `GET /eval`, `GET /eval/runs/{run_id}`, `GET /task-runs/{task_id}`, `GET /channels`, `POST /channels/{channel}` | P0 | J |
| Admin | `GET/POST /admin/persons`, `PATCH /admin/persons/{person_id}`, `GET/PUT /admin/settings` | P0 | B |
| | `GET /admin/audit` | P1 | B |
| Auth | `POST /auth/login`, `GET /auth/me`, `POST /auth/logout` | P0 | G |
| | `POST /auth/demo-switch` | P1 | G |
| PWA | `POST /pwa/session`, `GET /pwa/inbox`, `POST /pwa/checkins`, `/pwa/symptoms`, `/pwa/monthly`, `POST`/`DELETE /pwa/push-subscriptions` | P1 | G |
| Mock | `GET /mock/nikshay/patients/{nikshay_id}`, `GET /mock/nikshay/payments`, `POST /mock/nikshay/scenario` | P0 | K (`cm/api/routers/mock_nikshay.py`) |
| Identity | `POST /identity/resolve`, `GET /identity/unmatched` (admin) | P1 | G |
| Health | `GET /healthz`, `GET /readyz` | P0 | G |

---

## d. Final Pydantic schema list, by `cm/contracts/` file

The architecture's five files grow to **eight plus `tools.py`**. `api.py` would otherwise hold more than 100 models, and the split costs nothing to codegen. Shared `Literal` aliases live in `domain.py` and are imported everywhere.

**`domain.py`**
- **Enums/aliases:** `Role`, `Tier`, `ReporterMode`, `DoseStatus`, `ConsentSource` (`telegram, web, supporter, gmail, calendar, wearable, chemist, lab, portal`), `Purpose` (`daily_checkin, care_coordination, supporter_sharing, programme_monitoring`), `OutboundChannel` (`telegram, gmail, webpush, web_inbox, calendar`), `AgeBand`.
- **Core:** `Person`, `Patient`, `ConsentEvent`, `EventBase`.
- **`Event` union:** `DoseCheckin`, `SymptomReport`, `SupporterVisit`, `PillCount`, `Dispense`, `LabResult`, `WeightReport`, `PaymentReport`, `PortalPayment`, `PortalRegistration`, `WearableReading`, `ReviewDecisionEvent`, `ContextNote`, `IdentityLinked`, `BeliefRetired`, `Tombstone`, `CheckinPrompt`, `RegimenChange`, `ChannelUnreachable`, `HouseholdContactEvent`, `ConsentEvent`.

**`memory.py`**
- **Engine:** `FeatureVector`, `Detection`, `Belief`, `BeliefDetail`, `BeliefPin`, `Conflict`, `ConflictDetail`, `RiskScore` (+ `p_miss7`, `miss7_ci_low`, `miss7_ci_high`), `Driver`.
- **Snapshot:** `TrustLine`, `Coverage`, `MemorySnapshot` (+ `trust`, `headline`, `recommendation`, `computed`, `sim_day`), `LensComparison`, `FunnelSeries`, `TimelineItem`, `CitationRef`.
- **Narration:** `EvidenceBundle`, `NarrationRequest`, `NarrationDraft`, `MemoryCard`, `Sentence`, `ValidatorReport`.
- **Nightly:** `NightlyReport`. `InMemoryResult` is a frozen dataclass, not Pydantic.

**`review.py`**
- **Enums/aliases:** `ReviewKind` (K1), `ApprovalStatus`, `DecisionAction`, `DeliveryState`.
- **Queue and decisions:** `Recipient`, `EvidenceItem`, `ProposalOut`, `ReviewItem`, `ReviewQueueOut`, `ReviewItemDetail`, `DecisionRecord`, `ReviewDecisionIn`, `ExpiredDecision`, `ReviewDecisionOut`, `BulkDecisionIn`, `ReviewMetrics` (P1).
- **Templates and outbox:** `Template`, `TemplateDraftIn`, `TemplatePreview`, `OutboxItem`, `OutboxRef`, `SendResult`.
- **Digest and reply:** `DigestItem`, `ReplyCommand`, `ReplyParse`.

**`agents.py`**
- **Tasks:** `TaskEnvelope`, `TaskResult`, `ResumeEnvelope`, `ToolContext`, `AgentTaskIn`, `TaskAccepted`, `TaskStatus`.
- **Intake and identity:** `RawInbound`, `ParsedInbound` (events, without `FreeTextNote`), `IdentityQuery` (+ `nikshay_id`, `lab_id`), `IdentityMatch`.
- **Investigation:** `InvestigationRequest`, `InvestigationReport`, `Finding`, `HypothesisRequest`.
- **Q&A:** `QueryIn`, `QueryAnswer`, `ToolCallUsed`, `AnswerTable`.
- **Judge and guards:** `JudgeVerdict`, `TokenMap`, `InjectionScan`.

**`api.py`** (common, webhooks, ingest, channel payloads)
- **Common:** `Problem` (+ `status`, `code`), `Page[T]`, `LiveEvent`.
- **Ingest:** `IngestReceipt` (+ `duplicates`, `review_items`, `task_id`), `LabResultIn`, `SupporterCheckinIn` (+ `client_uuid`, `payment`), `WearableBatchIn` + `HcRecord` (P1), `PortalPaymentIn`, `PortalRegistrationIn`, `ChemistCsvRow`, `HouseholdContactIn`, `HouseholdContactOut`, `LabReportExtraction` + `LabField` (P1).
- **Webhooks and channels:** `PubSubPush`, `GmailNotification`, `GmailFetchIn`, `TelegramUpdate` (subset), `TgCallback`, `CalendarEventSpec`, `ChannelProfile`.
- **Supporter:** `VisitList`, `VisitItem`.
- **PWA (P1):** `MagicLinkExchangeIn`, `PwaInbox`, `PwaCheckinIn`, `PushSubscriptionIn`.

**`dashboard.py`**
- **Patients:** `PatientSummary`, `PatientDetail`, `PatientSeries`, `SparkPoint`, `FlagChip` (rule `R1`…`R6`), `ChannelChip`, `HouseholdSummary`, `EventOut`.
- **Clinic and district:** `ClinicSummary`, `SuppressedInt`, `DistrictSummary` (+ 03 RFC fields), `BlockRow`, `TrendSeries`, `PaymentStuckRow`.
- **P1:** `CascadeStage`, `PharmacyRow`, `SupporterActivityRow`, `MonthlyReport` (01's `DistrictMonthlyReport` is merged into it), `RevealIn`, `RevealOut`.

**`admin.py`**
- **Auth:** `LoginIn`, `TokenOut`, `Me`.
- **Persons:** `PersonAdminIn`, `PersonAdminOut`, `PersonAdminPatch`.
- **Settings:** `RuleThresholds`, `DetectorParams`, `SettingsIn`, `SettingsOut`.
- **Consent and erasure:** `ConsentState` (+ `ledger`), `ConsentEventIn` (source = `ConsentSource`, `via: str` matching `^(console|telegram|web|paper|supporter:S-\d+)$`, `notice_version`), `ConsentEventOut`, `ErasureRequestIn`, `ErasureRequestOut`.
- **Audit:** `AuditEntry` (P1).

**`evalsim.py`**
- **Sim:** `SimClock` (+ `max_computed_day`, `escalation_offset_hours`, `offline`, `status`), `SimRunOut` (+ `task_id`), `SimInboxItem`, `SimReplyIn`, `EscalationOffsetIn`, `SimInjectIn` (P1).
- **Runs:** `TaskRunStatus` (field **`state`**).
- **Eval:** `EvalReport`, `EvalRunStatus{run_id, seed, status, report?}`.
- **Eval sub-models:** `CurvePoint{day, model: MetricCI, pop_avg: Metric, last_week: Metric, n_pos}`, `MetricCI{brier, auroc?, brier_ci, auroc_ci?}`, `Metric{brier, auroc?}`, `FunnelPoint{day, mean_ci_width, coverage90}`, `FactsScorecard{by_pattern: dict[PatternKind, PatternScore], totals: PatternScore, missed: list[MissedPattern], no_pattern_fp_rate}`, `PatternScore{planted, caught, false, false_retired, missed, precision, recall, median_days_to_detect}`, `MissedPattern{patient_token, pattern, reason: Literal["insufficient_observations","below_threshold","wrong_subject"], detail?}`, `RuleScore`, `Safeguards`, `Timings`, `SafetyCounters`.
- **Channels:** `ChannelStatus`, `ChannelToggleIn`.

**`tools.py`** (`typing.Protocol`, `runtime_checkable`; each lane ships a fake in its `fakes.py`)
`EventStore`, `ConsentReader`, `Clock`, `TaskQueue`, `TaskRunsRepo`, `ApprovalsRepo`, `OutboxRepo`, `SettingsRepo`, `HouseholdRepo`, `ModelFactory`, `MemoryEngine`, `Reconciler`, `Validator`, `IdentityResolver`, `ReviewService`, `TelegramClient`, `GmailClient`, `CalendarClient`, `Router`.

---

## e. Final lane plan for tomorrow

**Shape:** 14 build lanes plus Opus (L0 and Integration).

**Changes from the architecture's 11 lanes:**
- **H** splits into **H1/H2**, as the dashboards spec proposed.
- **E** splits into **E** (runtime, gate, tools) and **N** (narrator and sub-agents). E alone was 18 P0 hours on the critical path.
- **F** splits into **F** (Telegram, Supporter, router, household) and **M** (Gmail, consent, calendar). F alone was 26 P0 hours.
- **B** takes the district/admin backend as a second phase, after the generator lands.
- **J** takes the sim, eval and channels routes.

**Times:** Hours are P0 agent-hours. ★ = on the critical path; ◆ = no slack (size-critical). Window = wall clock. Feature freeze is **H22**.

| Lane | Owner | Exclusive dirs / files | Implements | P0 h | Start → done | Depends on |
|---|---|---|---|---|---|---|
| **L0 Contracts** ★ | **Opus** | `cm/contracts/`, `fixtures/` (goldens, `openapi.json`), `cm/store/migrations/versions/0001_core.py`, `CLAUDE.md`, `Makefile`, `pyproject.toml`, `contracts/CHANGES.md`, `scripts/check_ownership.py` + `scripts/lanes.yaml`, `cm/agents/prompts/`, `cm/agents/playbooks/`, `docs/maths.md`, `docs/generator.md` | §b–§d of this doc; 02 prompts/playbooks; 04 F2 label spec | 2.5 + 1.5 | H0 → H2.5 (tier 1, tag `contracts-v1`); H4 (tier 2, `v1.1`); prompts H6 | — |
| **A Data core** ★ | Sonnet | `cm/core/`, `cm/store/` (except `0001`, `0005`) incl. `events_repo`, `as_of`, `consent`, `projections`, `task_runs_repo`, `approvals_repo`, `outbox_repo`, `settings_repo`, `household_repo`, migrations `0002`–`0004`; `cm/jobs/migrate.py` | arch §5, §8A; 02 F3; 04 F3 (clock, local queue), F4 (A part), F5 (`llm.py`, `retry.py`), F6 (config, tokenize, crypto, audit, `erase_person`), F7 (JSON logs, metrics); RAG DDL | 11 | H2.5 → **H7** core; H13 rest | L0 |
| **B Sim + seed → console backend** | Sonnet | `cm/sim/` (except `replay.py`, `cassette.py`, `sim_channels.py`), `cm/jobs/seed.py`; phase 2: `cm/api/routers/{dashboard,admin,consent,templates}.py`, `cm/api/suppress.py`, `cm/store/migrations/versions/0005_views.py` | 04 F1 (+ household members, cascade stages, unmatched pharmacy rows, Ni-kshay seed, `RegimenChange`); 03 §4/§7 backend P0, consent and erasure routes, views and notify triggers | 7 + 5.5 | H2.5 → **H5 fixture drop** → H10 seed job; H10 → H16 phase 2 | L0; A `bulk_append` (H7) |
| **C Memory engine** ★ | Sonnet (Opus maths) | `cm/memory/`, `models/` | 02 F4, F5, F10, F11; M1 `run_in_memory`; M4 `miss7` head. P1: M7 what-if, `wearable_ask_flag` | 12.5 | H3 → H5 (B fixtures) → **H14** risk + MC CI → H16 | A `query` (H7), B fixtures (H5) |
| **D Rules + validator + identity** | Sonnet | `cm/rules/`, `cm/validator/` (incl. `injection.py`), `cm/identity/`, `tests/redteam/` | 02 F6 + **R6** + M3, F7 validator, F12 injection; 01 F12 | 9.5 | H2.5 → H13 | L0; A `fast_path` hook |
| **E Runtime + gate + tools** ★ | Sonnet (Opus reviews resume) | `cm/agents/{orchestrator,runtime,gate,schema_guard}.py`, `cm/tools/{guard,registry,patient,detectors,review,messaging}.py`, `cm/jobs/sweeper.py` | 02 F1, F8, F12 (PII middleware, schema guard); 04 F4 E part (`run_job`, heartbeat, sweeper six duties); M8 review-graph path | 10 | H3 → H14 (fakes) → **H17** live resume | L0; A repos; D validator (fakes) |
| **N Narration + sub-agents** ★ | Sonnet (Opus prompts) | `cm/agents/subagents/`, `cm/tools/{dashboard,guidelines}.py` | 02 F2 P0 (intake, narrator graph, drafter, memory-curator), F7 narrator graph, F9 Store projection. P1: pattern-investigator, dashboard-query, `search_guidelines` | 9 | H3 → H14 (fixtures) → **H16** on real L2 | L0; D validator; C snapshot |
| **F Telegram + Supporter + router** ◆ | Sonnet | `cm/channels/{telegram,tg_*,binding,supporter_web,household,factory,webpush}.py`, `cm/router/` (except `degrade.py`), `cm/router/templates/` loader (not the YAML content) | 01 F1, F3, F13 capture, router §3.11, `CheckinPrompt` append, drainer throttle | 16.5 | H2.5 → H19 | L0; A repos; G webhook route (fake) |
| **M Gmail + consent + calendar** | Sonnet | `cm/channels/{gmail,gmail_parse,gmail_reply,calendar,consent_flows}.py`, `cm/router/degrade.py` | 01 F4 digest, F5, F6 (`family_screen` P0), F11 | 11.5 | H2.5 → H15 | L0; G `decide()` (fake); A consent |
| **G Core API** ★ | Sonnet | `cm/api/` (except B's, J's and K's routers and `suppress.py`), `cm/review/` | arch §6.1–6.4, §6.7 auth; 03 §1/§2/§3 backends, §8 auth, `/stream`; 04 F6 webhook auth; K2 `decide()` | 12.5 | H2.5 → **H4 route stubs → `openapi.json`** → H17 | L0; everything via fakes |
| **H1 Doctor console** ★◆ | Sonnet | `web/` shell (`package.json`, `src/{main.tsx,router.tsx,api,auth,realtime,components,styles,mocks}`), `web/src/pages/{Login,ReviewQueue,Patients,Patient,Lens,Timeline}/` | 03 §0 foundation, §1, §2 (list, overview, drawer; timeline = P1 tail), §3, §8 frontend | 19.5 | H2.5 → H22 | L0 fixtures; G `openapi.json` (H4) |
| **H2 District + demo + admin** | Haiku (H1 reviews at H10/H14) | `web/src/pages/{District,Eval,Sim,Admin,Ask,Supporter}/`, `web/src/features/patient-tabs/` (Charts, Consent, Household) | 03 §4, §6, §7 frontends, Charts tab, consent/household panels; 04 F3 phone panels | 14 | H4 → H20 | H1 shell (H6); L0 tier-2 fixtures |
| **I Infra + local + obs** | Haiku + human | `infra/`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `requirements*.txt` (exported), `scripts/` (except L0's) | 04 F8, F9, F7 (alerts P1); a6 I1–I11 | 7.5 | **H0.5** → H8, then each merge | none |
| **J Eval + replay + offline** | Haiku (Sonnet for `sim_channels`) | `cm/eval/`, `cm/sim/{replay,cassette,sim_channels}.py`, `cm/jobs/eval_job.py`, `cm/api/routers/{sim,eval,channels}.py`, `tests/replay/` | 04 F2, F3; 03 §6 backend glue | 10.5 | H3 → H12 (fake engine) → H18 | B generator (H5); C `run_in_memory` (H12); A clock and tasks |
| **K Content + mock feeds + RAG seed** | Haiku | `cm/router/templates/*.yaml`, `data/guidelines/`, `fixtures/text_bank.json`, `cm/channels/{chemist_csv,portal_mock}.py`, `cm/api/routers/mock_nikshay.py`, `cm/rag/`, `docs/{dpdp_notice_v1,breach_plan}.md` | 01 F7, F10, every template key (incl. `family_invite`, `gmail_echo`, `danger_ack`, the Red alert template); RAG-lite guideline seed | 8.5 | H2.5 → H12 | L0; A (`append_event`, 0004) |
| **Integration** ★ | **Opus** | merges, `tests/integration/` | H6 / H10 / H14 checkpoints; H16–H22 Ravi loop on GCP; replay goldens | 8+ | H6 → H22 | all |

**Build P0 total ≈ 166 agent-hours, plus about 12 Opus hours.**

**Critical path (≈ 20.5 h, about 1.5 h slack before H22):**
L0 (2.5) → A `query`/`append`/repos (4.5, H7) → C detectors + risk + MC CI on the real store (7, H14) → N narrator on real L2 + E interrupt/`decide()`/resume (3, H17) → G and H1 live wiring of queue and Lens (1.5, H18.5) → Ravi day-60 loop on Cloud Run (2, H20.5).

**Size-critical lanes:** H1 (19.5 h in a 19.5 h window) and F (16.5 h).

**Watch:** C at H14, E resume at H17, H1 at every checkpoint. **If C slips past H14:** N and H1 use the Ravi fixture snapshots, C lands by H17, and Integration absorbs it.

### Hour-0 contract-freeze checklist (Opus)

| ✓ | By | Item |
|---|---|---|
| ☐ | H0:15 | Repo from `main`; directory scaffold for every lane; `scripts/lanes.yaml` with the exclusive paths in the table above; ownership pre-commit hook on |
| ☐ | H0:20 | `CLAUDE.md` updated: 14 lanes, `task_runs` (not `jobs`), `approval_id`, `recorded_at`, OpenAI/DeepSeek only, `cm/review/decide.py` is the only decision path, citation refs E/B/C/R/G/D |
| ☐ | H1:30 | **Tier-1 contracts:** `domain.py`, `memory.py`, `review.py`, `agents.py`, `api.py`, `tools.py` exactly per §d, with shared `Literal`s in `domain.py` |
| ☐ | H2:00 | `0001_core.py`: every §b table, UNIQUE/CHECK constraints, the outbox CHECK + trigger stub, INSERT-only trigger stubs; `make contracts-check` green against a compose Postgres |
| ☐ | H2:15 | `docs/maths.md`: priors, thresholds, lifecycle, CUSUM k/h, labels M5, seed ranges, R1–R6 parameters, `frozen_spec_hash` recorded. `docs/generator.md`: pattern rates, Ravi overlay table, household members for Ravi (Sunitha, Meena, son) |
| ☐ | H2:30 | **Tier-1 fixtures:** `MemorySnapshot_ravi_d{3,60}`, `LensComparison_ravi_3_60`, `FunnelSeries_ravi`, `ReviewQueueOut_demo` (1 Red / 6 Amber / 23 Green), `ReviewItemDetail_ravi_card_d60`, `ReviewItemDetail_kavya_red`, `PatientSummary_list_clinic`, `PatientDetail_ravi_d60`, `TimelineItem_list_ravi`, `EventOut_chemist_csv_d44`, `TaskEnvelope_*`, `household_ravi.json`, `visit_list_approved_d60.json`, 10-line `seed42_events_sample.jsonl`. **Tag `contracts-v1`; create the 14 worktrees** |
| ☐ | H4:00 | **Tier-2 contracts:** `dashboard.py`, `admin.py`, `evalsim.py`; fixtures `DistrictSummary_demo`, `BlockRow_list_demo`, `PaymentsStuck_demo`, `EvalReport_seed42` (M6 shape), `SimClock_d60`, `Me_*`, `SettingsOut`, `TaskRunStatus_*`. Accept G's route stubs → freeze `fixtures/openapi.json`. **Tag `contracts-v1.1`**; all lanes rebase |
| ☐ | H6:00 | Prompts and playbooks: `orchestrator.md`, `narrator.md` (doctor + Supporter), `drafter.md`, `intake.md`, `query.md`, `AGENTS.md`, playbooks per task type (`ingest_event`, `nightly_patient`, `investigate`, `prepare_visit_list`, `doctor_digest`, `consent_change`) |
| ☐ | H6:00 | Integration 1: A + B (generator) + D + K merged; seed job runs on Cloud SQL; I's skeleton `cm-api`/`cm-worker` deployed |

---

## f. Remaining contradictions and their resolutions

| # | Contradiction | Resolution |
|---|---|---|
| C1 | Arch still said `jobs.heartbeat_at` (§8A.5), `jobs.cost_usd` (§9.1), ER entity `JOB`, metric `jobs_by_state`, CLAUDE.md `jobs.heartbeat()`; spec 04 used `jobs` throughout | All renamed to `task_runs` in both docs (done). Metrics are `task_runs_by_state`, `task_runs_running`, … |
| C2 | `tool_call_id` (02, arch §11 #12) vs `interrupt_id` (arch §5) | `interrupt_id`; the value = the HITL tool-call id (T2) |
| C3 | `proposal`/`due_at`/`redraft_no` (02) vs `payload`/`expires_at`/`redraft_count` (arch) | Arch names; `due_at` added as a stored column alongside `expires_at` |
| C4 | Outbox written by the decision transaction (arch, 03, 04) vs by the resumed tool body (02) | The decision transaction (K3) |
| C5 | Two `EvalReport` shapes (03 flat, 04 nested) | 04 nested + `facts.totals` + `safety` (M6) |
| C6 | Judge re-roll via `/sim/reset` → seed → nightly → eval (03) vs in-memory `/eval?seed` (04) | In-memory `/eval?seed`; `/sim/reset` never runs eval (P2) |
| C7 | Eval 202 location `/task-runs/{id}` (03) vs `/eval/runs/{id}` (04) | `/eval/runs/{id}` |
| C8 | 03 lets a judge pick any 4-digit seed | Seeds < 2000 → 422 (except 42, flagged); the UI input enforces ≥ 2000 |
| C9 | argon2 (03) vs scrypt (04) | `hashlib.scrypt` |
| C10 | `JWT_SECRET` (03) vs `JWT_SIGNING_KEY` (arch, 04) | `JWT_SIGNING_KEY` |
| C11 | `persons.token_version` vs `auth_credentials.token_version` (03 says both) | `auth_credentials` only |
| C12 | RAG `[C:chunk_id]` vs arch `C` = conflict | `G` = guideline chunk, `D` = patient-document chunk |
| C13 | RAG `received_at`, `cm/db/migrations`, a SQL tool, 41 P0 hours | `recorded_at`; `cm/store/migrations`; SQL tool rejected; RAG-lite scope (T6) |
| C14 | `FreeTextNote` in `ParsedInbound` but not in the `Event` union | `ContextNote` (E7) |
| C15 | Bucket `caremem-uploads` (01) vs `$PROJECT-cm-docs` (04) | `$PROJECT-cm-docs` with prefixes (I4) |
| C16 | 00 conventions: queues `outbox-send`, topic `gmail-events`, roles `district_officer`, `users` table, evaluator as an agent | Arch names: `outbound`, `gmail-push`, `sts`/`dto`, `persons` + `auth_credentials`; the evaluator is **not** orchestrated |
| C17 | R6 id `R6_contacts_unscreened` (01) vs `R6_contacts` (03); "Amber conflict" (01) vs "Amber approval" (03, addendum) | Id `R6`; an Amber conflict **and**, on open, one deterministic `kind=conflict` Amber approval (M8) |
| C18 | Queue rates "3/s, 5 concurrent" (arch §2b, 02) vs "2/s, 4 concurrent" (arch §8A.3, §12, 04) | 2/s, 4 concurrent (I11) |
| C19 | Pub/Sub fetch task name `gmail-{historyId}` (01) vs `gmail-fetch-{historyId}` (04) | `gmail-fetch-{historyId}`; per-message `task_runs` id `gm-{gmail_message_id}` |
| C20 | Chemist event key `chem:{chemist}:{bill}:{line}` (01) vs `csv:{chemist}:{row_sha1}` (04) | `chem:{chemist_id}:{bill_no}:{line_no}`; when there is no bill number, `chem:{chemist_id}:sha1:{row_sha1}` |
| C21 | Task id / thread id formats | `task_id` is colon-free: `{task_type}-{token\|all}-d{day}-{hash8}`, `resume-{approval_id}`, `send-{outbox_id}`, `nudge-{outbox_id}`, `drain-{channel}-{epoch_min}`, `nightly-{token}-d{day}`, `tg-{update_id}`, `{task_id}-a{n}` (sweeper only). `thread_id` keeps colons: `{task_type}:{token}:{day}:{uuid8}` |
| C22 | Sim play loop: 2 s (03) vs 400 ms (04) | 400 ms, fast mode (clock only) |
| C23 | Three outbox `dedup_key` formats (arch, 01, 04) | `{decision_id\|template_key}:{recipient_id}:{channel}:{for_date}[:{n}]` |
| C24 | Approval ladder: Amber reminder at "50% TTL" / backup at "100%" (04) vs 24 / 36 / 48 h (arch) | 24 h reminder, 36 h backup doctor, 48 h `expired`; Red → STS at 4 h, stays open |
| C25 | identity-resolver P1 (02) vs F12 P0 (01) | P0 for the rules and bands; the LLM one-line explanation is P1 |
| C26 | pattern-investigator P1 (02) but in the arch's nightly flow | P1. The `nightly_patient` playbook skips it when absent; the narrator uses `RiskScore.drivers` + beliefs directly |
| C27 | `dashboard_question` as an orchestrated task (arch) vs inline in `cm-api` (03) | Inline (P8) |
| C28 | `ModelFallbackMiddleware` (02) vs `with_fallbacks` (arch, 04) | Agents use `ModelFallbackMiddleware` ⚠ (keeps `bind_tools`); direct structured calls (narrator draft, judge) use `with_fallbacks`. Spend-cap and auth errors are never handled by either |
| C29 | Store index `fields: ["before"]` (02) vs `["text"]` (04) | `["text"]` (M10) |
| C30 | Consent `source` vocabularies (01 vs 03) and `via` (`supporter:{sid}` vs a Literal) | 01's list; `via` is a constrained string (§d `admin.py`) |
| C31 | 03 `Channel` literal mixes sources and channels | Split into `ConsentSource` and `OutboundChannel` |
| C32 | Supporter PWA pages "owned by the Supporter/PWA group" (03) vs `web/src/pages/Supporter` in 01 | H2 owns them; P1 (Telegram Supporter mode is the P0 path) |
| C33 | `ReviewDecisionOut.via` lacks `sweeper` | Add `sweeper` |
| C34 | `/sim/advance` runs the nightly inside `cm-api` (60 s timeout) | `mode=full` triggers a `cm-nightly` execution (I3 grants it) |
| C35 | Haiku as a runtime sub-agent model (arch §2c, §11 #7) | `WORKER_MODEL` (Z6) |
| C36 | Arch "Claude/Gemini optional", `ANTHROPIC_API_KEY`/`GOOGLE_API_KEY` secrets, `aiplatform` API | Removed (Z6) |
| C37 | Contract file count: 5 + `tools.py` (arch) vs > 100 models | 8 + `tools.py` (§d) |
| C38 | 04 F7 reads cost from `jobs`; RAG §7 logs latency to `jobs` | `task_runs.cost_usd` / `tokens_*` (the RAG doc wording is superseded by Z2) |
| C39 | 04 `.env.example` lacks `DEMO_MODE`, `VAPID_*` | I adds `DEMO_MODE=0` and (P1) `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` |
| C40 | `cm-nightly` "5 rules" (arch §2f, §3.4) | 6 rules (R6 added) |

---

## g. Feasibility check and cut list

**Raw P0 hours as written in the specs:**

| Source | P0 h |
|---|---|
| 01 channels | 32.5 |
| 02 AI core | 35.5 |
| 03 dashboards | 48 |
| 04 platform | 38.5 |
| RAG doc | **41** |
| L0 + Integration + content (arch only) | 13.5 |
| **Total** | **≈ 209 h** |

**After de-duplication:**
- Evaluator counted in 02 and 04: −1
- Tokenisation in 02 F12 and 04 F6: −1
- Gate vs decision service: −1
- Runtime in 02 F1 and 04 F4: −1
- RAG → RAG-lite (41 → 3.5 P0): −37.5

**Result ≈ 166 build hours + about 12 Opus hours**, which matches the lane tally in §e.

**Capacity:** a lane realistically works from H2.5 to H22 = 19.5 h, not 22 h.
- 11 lanes × 19.5 h = 214 h.
- 14 lanes × 19.5 h = 273 h.

**Verdict:**
- **Raw hours:** they fit on paper in 11 lanes (166 of 214 h, 78% utilisation).
- **Lane shape:** the original lanes did **not** fit. Old H was 24.5 h, F 26 h, E 18 h and G 18 h, all against a 19.5 h window. Hence the four splits in §e. After the splits, the largest lane is H1 at 19.5 h.
- **Overrun:** at a typical 1.3× estimate overrun, total demand ≈ 216 h (79% of 273 h). That is feasible, but H1 and F have no slack. The cut list below is therefore **pre-authorised**: Opus triggers cuts at the H10 and H14 checkpoints without further discussion.

**Already outside P0 (never start before H18 unless a lane is idle):** Dashboard Q&A; pattern-investigator; `search_guidelines` and patient-document RAG; Patient PWA (F2) and Supporter PWA; lab vision (F8); wearables (F9); district cascade, pharmacies, Supporter table and monthly report; admin thresholds editor and audit viewer; review metrics; scenario injector; demo-switch; identity LLM explanation; Calendar beyond `family_screen`.

**Cut list. Cut from the top; every cut is final once made:**

| Order | Cut | Saves | What replaces it on stage |
|---|---|---|---|
| 1 | Channel kill switches + what-if (`/channels`, `exclude_sources`, M7) | 3 h (H2 1.5, C 0.5, J 0.5, G 0.5) | The consent-withdrawal toggle (real F11 path) + the `trust.html` slide |
| 2 | Timeline lanes tab (H1) | 2 h | Overview citations + `EventDrawer` |
| 3 | Charts tab (H2) | 2 h | The refill-gap conflict's evidence in the drawer |
| 4 | Admin users & roles page (H2 + B) | 2 h | Seeded users; keep templates approve + consent |
| 5 | Escalation fast-forward + sweep-now | 1 h | A pre-escalated Red item in the seed (`escalated_at` set) |
| 6 | SSE `/stream` (G + H1) | 3 h | 5 s polling on the queue; Beat 7b flips within 5 s |
| 7 | Supporter Telegram ForceReply numbers (pill count, weight) | 1.5 h | Visited buttons only; the pill count goes through `/ingest/supporter` |
| 8 | F13 Telegram wizard → a 3-step minimal flow (relation, age band, a single "any symptom?" yes/no) | 0.75 h | Same events, table, R6 and KPI (P0 stays intact) |
| 9 | Gmail approve-by-**reply** (F5 inbound) | 5 h | Digest email outbound only; the doctor approves in the console. Last resort, because it removes Beat 7b's best moment |

**Never cut:**
- Memory Lens (two panels, slider, funnel)
- Review queue + doctor gate + outbox CHECK
- Cite-or-cut validator + template fallback
- Telegram check-in with `CheckinPrompt`
- R1–R6
- Household table + R6 + "contacts screened %" KPI
- `/eval?seed` re-roll + learning curve + missed list
- `CM_OFFLINE` replay of the Ravi day-60 loop
