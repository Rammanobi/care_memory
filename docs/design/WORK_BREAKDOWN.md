# CareMemory: work breakdown (phases → tasks → steps)

**Author:** delivery lead, 24 Oct 2026 (pre-build).
**Use with:** `PHASES_SCRIPT.md` (when and how each phase is presented to the owner), `INTEGRATION_DECISIONS.md` (IDD: names, lanes, cut list, which wins on any conflict), `CAREMEMORY_PHASED_ARCHITECTURE.md`, `feature_specs/01`–`04`, `TWIN_ACCOUNT_DEMO_PLAYBOOK.md`, `PREFLIGHT_AND_BRAINSTORM.md`, `UI_FEATURES_RESEARCH.md`, `caremem/MEMORY.md`, `caremem/CLAUDE.md`.
**This document schedules work that those documents already decided. It reopens nothing.** If a step here disagrees with IDD, IDD wins and this file gets a `fix-work-breakdown` note.

---

## The goal

**Win the Innovators Conclave 2026 hackathon with CareMemory, an AI care memory for TB treatment.**

To do that, we need a working end-to-end prototype, built in 36 hours on the floor, with these parts:
- **Opt-in check-ins on Telegram.** Patient and Supporter both use it, button-first, and no message ever names the disease.
- **Gmail.** A doctor digest goes out by email, and the doctor can approve by replying to it.
- **A doctor review queue behind a database-enforced doctor gate.** The outbox CHECK and trigger, plus `decide()` as the only way to record a decision.
- **A memory engine with cited contradiction flags.** Beliefs, risk with intervals, rules R1–R6, and a cite-or-cut narrator.
- **A Day 3 vs Day 60 Memory Lens**, plus the twin-account demo (P1).
- **A district dashboard**, including the contacts-screened % KPI.
- **A 60-day evaluation the judges can re-roll with their own seed** (`/eval?seed≥2000`).

**How the judges score:**

| Round | Weight | What wins it |
|---|---|---|
| Idea and Solution Presentation | 15% | A clear user and problem, the problem-statement mapping, safety ("the AI drafts, the doctor decides"), feasibility |
| Prototype Development and Integration | 35% | Real integrations, live on GCP: a Telegram tap → event → memory → queue → approve → Supporter message |
| Final Demo and Market Readiness | 50% | A live, reliable 3-minute demo, a judge-chosen seed, an honest list of misses, a business case and a specific pilot ask |

**Design rule for this breakdown:** anything that does not move one of those three scores, or protect the live demo, is P1 or cut.

---

## Conventions used in every task

- **Clock.** H0 = 10:00 Sat 24 Oct (assumed; re-base when the organisers announce the real start). H36 = 22:00 Sun 25 Oct. "H6 (16:00)" means hour 6 = 16:00 Saturday.
- **Lanes** are from IDD §e:
  - L0 Contracts (Opus)
  - A Data core
  - B Sim + seed → console backend
  - C Memory engine
  - D Rules + validator + identity
  - E Runtime + gate + tools
  - N Narration + sub-agents
  - F Telegram + Supporter + router
  - M Gmail + consent + calendar
  - G Core API
  - H1 Doctor console
  - H2 District + demo + admin
  - I Infra
  - J Eval + replay + offline
  - K Content + mock feeds + RAG seed
  - INT Integration (Opus)
  - COORD = the coordinator session
  - OWNER = the human owner or a teammate the owner delegates to
- **Models.** Opus thinks, freezes contracts, merges and reviews the gate and validator. Sonnet builds anything with non-trivial logic. Haiku builds well-specified, test-defined work. Runtime models inside the product are OpenAI or DeepSeek only (Z6).
- **Every lane task also does three things.** These are not repeated in each STEPS list:
  1. It follows `caremem/MEMORY.md` Rule 1: an OpenSpec change is proposed, implemented, validated and archived.
  2. It commits to `lane/<lane>` after each step group, and at least every 45 minutes.
  3. It keeps a `RESUME POINT` block in its lane `NOTES.md`.
- **"Done when"** is a command, test or demo that anyone can run. `make check` = ruff + pytest + the ownership check inside the lane worktree.
- **Effort** is agent-hours for build tasks and person-hours for owner tasks.
- **Task IDs** are `<phase>.<n>`. A lane's long job is split across phases, so each task has a hard end inside its phase.

---

# Phase 0: Owner pre-flight (tonight, Fri 20:00 → Sat 10:00 = T-14h → H0)

**Phase goal.** By H0, everything that needs a human, a browser, a payment card or a console click is done:
- keys stored in Secret Manager;
- spend caps set;
- Cloud SQL up, with pgvector confirmed at version ≥ 0.7;
- both Telegram bots created;
- the Gmail refresh token minted;
- a hello-world `cm-api` answering on `*.run.app`;
- the `scaffold-v0` commit pushed;
- the organisers' answer on pre-built design written down;
- the team roles fixed.

**The coordinator runs on Sonnet all night**, so the Opus 5-hour window starts fresh at H0.

**Hours:** about 2.5 h of owner time and 2 h of Sonnet time, run in parallel.

### Tasks

#### 0.1 Switch the coordinator to Sonnet and open the ops log
- **Owner / model:** OWNER + COORD · Sonnet
- **Inputs:** today's last Opus 429 message (it gives the reset time)
- **Touches:** `caremem/docs/OPS_LOG.md` (new)
- **STEPS**
  1. Owner types `/model sonnet` in the coordinator session.
  2. COORD creates `caremem/docs/OPS_LOG.md` with sections: Clock, Usage resets, Model IDs, Done, Blockers, Decisions, Roster.
  3. Record today's Opus reset times, and the planned first Opus message at H0 (10:00).
  4. Record the assumed H0 and "re-base on organiser announcement".
- **Deliverable:** `OPS_LOG.md` containing the reset times
- **Done when:** `grep -n "Opus reset" caremem/docs/OPS_LOG.md` prints a line
- **Effort:** 0.1 h

#### 0.2 GCP project, billing, budgets, APIs; start Cloud SQL first
- **Owner / model:** OWNER (console clicks) + COORD (scripts) · Sonnet
- **Inputs:** a billing card; `infra/00_project.sh`, `infra/20_sql.sh`
- **Touches:** GCP project `caremem-hack`; `infra/vars.sh`
- **STEPS**
  1. Owner creates or links project `caremem-hack` to billing in the console.
  2. Owner sets budget alerts at ₹2,000 and ₹5,000.
  3. COORD runs `infra/00_project.sh` to enable every IDD API: Run, SQL Admin, Tasks, Pub/Sub, Scheduler, Secret Manager, Cloud Build, Artifact Registry, Gmail, Calendar.
  4. COORD runs `infra/20_sql.sh` **now**. It creates `cm-pg` on PG16 with `--edition=ENTERPRISE` and `db-custom-1-3840` in asia-south1 (IDD I6). The create takes 10+ minutes, so everything else runs meanwhile.
  5. COORD records the operation id in `OPS_LOG.md`.
- **Deliverable:** a billed project, APIs on, and the SQL create operation running
- **Done when:** `gcloud sql operations list --instance=cm-pg --limit=1` shows `RUNNING` or `DONE`
- **Effort:** 0.25 h

#### 0.3 LLM keys, spend caps and exact model IDs
- **Owner / model:** OWNER picks, COORD edits · Sonnet
- **Inputs:** OpenAI and DeepSeek dashboards; the OpenAI models page
- **Touches:** `caremem/.env` (git-ignored), `caremem/infra/env/{api,worker,jobs}.env.yaml`
- **STEPS**
  1. Owner creates the OpenAI key, plus the DeepSeek key if used. Keys are pasted only into gcloud prompts or `.env`, **never into chat**.
  2. Owner sets hard monthly caps (suggested $40 each) and notes the OpenAI RPM/TPM tier.
  3. Owner copies the exact model IDs from the models page (never from memory):
     - `ORCHESTRATOR_MODEL` and `VISION_MODEL`: one flagship tier;
     - `WORKER_MODEL` and `JUDGE_MODEL`: `deepseek:deepseek-chat`, or a small OpenAI model if DeepSeek is skipped;
     - `FALLBACK_MODEL`: the small OpenAI model;
     - `EMBEDDING_MODEL`: `openai:text-embedding-3-small`.
  4. COORD writes the IDs into `.env` and the three env YAMLs, and opens the OpenSpec change `change-set-model-names`.
  5. COORD records the RPM tier in `OPS_LOG.md`. It sizes `max-concurrent-dispatches` later.
- **Deliverable:** model IDs set and spend caps visible in the dashboards
- **Done when:** `grep -rn "<.*-model>" infra/env .env` prints nothing
- **Effort:** 0.3 h

#### 0.4 Telegram bots and the judge QR code
- **Owner / model:** OWNER · Sonnet helps
- **Inputs:** BotFather; three demo phones
- **Touches:** Secret Manager (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`); `caremem_deck/project/slides/demo.html`
- **STEPS**
  1. Create the demo bot "Daily Health Check Demo" in BotFather. Turn `/setprivacy` on and `/setjoingroups` off.
  2. Create a second dev bot for local ngrok testing, so it never fights the production webhook (spec 04 D12).
  3. Generate `TELEGRAM_WEBHOOK_SECRET` with `python -c "import secrets;print(secrets.token_urlsafe(32))"`. Store both tokens and the secret as secrets in task 0.6, never in chat.
  4. Log Telegram in on three phones: Ravi, Lakshmi and the doctor.
  5. COORD generates a QR code for `t.me/<bot>?start=DEMO-RAVI`, replaces `[QR code]` in `demo.html`, and queues an A5 print.
- **Deliverable:** two bots, three logged-in phones, and the QR code on the slide
- **Done when:** sending `/start` to the bot gets the BotFather default reply, and `grep -n "\[QR code\]" caremem_deck/project/slides/demo.html` is empty
- **Effort:** 0.25 h

#### 0.5 Gmail demo inbox, OAuth client and refresh token (with the Calendar scope)
- **Owner / model:** OWNER + COORD · Sonnet
- **Inputs:** a new Google account "CareMemory clinic inbox"; the doctor test address; `infra/gmail_auth.py`
- **Touches:** OAuth consent screen (External/Testing); Secret Manager (`GMAIL_OAUTH_CLIENT_JSON`, `GMAIL_REFRESH_TOKEN`)
- **STEPS**
  1. Owner creates the demo Gmail account and a second "doctor" test address.
  2. Owner configures OAuth consent as External/Testing and adds both as test users.
  3. Owner creates a Desktop OAuth client and downloads the JSON (stored as a secret, not committed).
  4. COORD runs `python infra/gmail_auth.py` with scopes `gmail.send`, `gmail.modify` and `calendar.events`. The owner completes the browser consent. The script prints the refresh token to the terminal only.
  5. Owner creates the "CareMemory clinic" calendar on the demo account.
  6. Note in `OPS_LOG.md`: the token is valid for about 7 days, so re-mint it if it is older than 5 days.
- **Deliverable:** a refresh token and a clinic calendar
- **Done when:** `python infra/gmail_auth.py --check` sends a test mail to the doctor address and lists the clinic calendar
- **Effort:** 0.3 h

#### 0.6 IAM, secrets, queues, Pub/Sub and the documents bucket
- **Owner / model:** COORD (scripts) + OWNER (pastes secret values into gcloud prompts) · Sonnet
- **Inputs:** `infra/10_iam.sh`, `30_secrets.sh`, `40_pubsub.sh`, `50_tasks.sh`
- **Touches:**
  - service accounts `cm-api`, `cm-worker`, `cm-jobs`, `cm-tasks-invoker`, `cm-pubsub-push`;
  - secrets;
  - queues `agent-runs`, `resumes`, `outbound`;
  - topics `gmail-push` and `dead-letter`;
  - bucket `caremem-hack-cm-docs`.
- **STEPS**
  1. Run `infra/10_iam.sh`. It grants per resource, never project-wide. It includes IDD I2 (`serviceAccountUser` on `cm-tasks-invoker`) and I3 (`run.developer` on `cm-seed`, `cm-eval`, `cm-nightly`, `cm-sweeper`).
  2. Run `infra/30_secrets.sh`. The owner pastes:
     - `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`;
     - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`;
     - `GMAIL_*`;
     - `JWT_SIGNING_KEY`, `DB_PASSWORD_APP`, `DB_PASSWORD_ADMIN`, `CM_KEK`.
  3. Run `infra/50_tasks.sh`, sized by the RPM tier:
     - `agent-runs` and `resumes`: 2/s, 4 concurrent, 6 attempts;
     - `outbound`: 5/s, 10 concurrent (IDD I11).
  4. Run `infra/40_pubsub.sh`: topic `gmail-push` with the Gmail publisher, topic `dead-letter`, and the `dead-letter-sub` pull subscription. The push subscription waits for the `cm-api` URL (task 0.8).
  5. Create the bucket `caremem-hack-cm-docs` in asia-south1 with uniform access, public-access prevention, and a 30-day lifecycle on `uploads/` (IDD I4).
- **Deliverable:** the runtime identity and messaging fabric
- **Done when:** `gcloud secrets list` shows all of them; `gcloud tasks queues list` shows the three queues; `gsutil ls -b gs://caremem-hack-cm-docs` succeeds
- **Effort:** 0.35 h

#### 0.7 Local environment, unverified pins and the deepagents signature
- **Owner / model:** COORD · Sonnet
- **Inputs:** `caremem/requirements*.txt`, `docker-compose.yml`, `web/package.json`
- **Touches:** `.venv/`, `requirements.txt` (only `# UNVERIFIED` lines), `cm/agents/NOTES.md`, `Dockerfile` (`uv` tag)
- **STEPS**
  1. Set up the environment: `python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt && .venv/Scripts/pip check`.
  2. For each failing `# UNVERIFIED` line, drop to the newest version **on the same major** that resolves. Record it as `fix-verify-pins` (`skip_specs: true`).
  3. Run `python -c "import inspect, deepagents; print(inspect.signature(deepagents.create_deep_agent))"` and save the output to `cm/agents/NOTES.md`. Repeat for `PostgresSaver.setup` and `ModelFallbackMiddleware`.
  4. Pin the exact `uv` image tag in the `Dockerfile`.
  5. Run `docker compose up -d db`, then `cd web && npm ci`, then `npx openspec validate --all`, which proves OpenSpec works on Windows.
- **Deliverable:** a reproducible local environment
- **Done when:** `pip check` is clean; `python -c "import langgraph, langchain, deepagents, fastapi"` exits 0; the compose DB reports healthy
- **Effort:** 0.4 h

#### 0.8 Cloud SQL ready: database, users, pgvector check, hello-world smoke deploy
- **Owner / model:** COORD · Sonnet
- **Inputs:** finished SQL instance (from 0.2), secrets (0.6)
- **Touches:** DB `caremem`, roles `cm_app`, `cm_engine`, `cm_reader`, `cm_admin`; Cloud Run service `cm-api` (hello world); push subscription `gmail-push-sub`
- **STEPS**
  1. Create the database `caremem` and the four roles, then run `CREATE EXTENSION vector;`.
  2. **Check pgvector:** `SELECT extversion FROM pg_extension WHERE extname='vector';`.
     - At least 0.7: keep `halfvec(1536)`.
     - Below 0.7: set `RAG_VECTOR_TYPE=vector` in the env YAMLs and log it (IDD T6).
  3. Deploy a hello-world `cm-api` (`make smoke-gcp`, or `gcloud run deploy cm-api --source . --region asia-south1`) with the Secret mount and the Cloud SQL connector. Start with `DB_CONNECT_MODE=connector`; fall back to `socket` if needed.
  4. Run `curl https://<cm-api>.run.app/healthz`, plus a `/readyz` that runs `SELECT 1`.
  5. Create the `gmail-push-sub` push subscription to `https://<cm-api>/webhooks/gmail` with:
     - OIDC as `cm-pubsub-push`;
     - `--dead-letter-topic=dead-letter --max-delivery-attempts=10 --ack-deadline=20`.
- **Deliverable:** a live run.app URL, proven against Cloud SQL
- **Done when:** both curls return 200, and the pgvector version is written in `OPS_LOG.md`
- **Effort:** 0.4 h

#### 0.9 Repo baseline: first commit, `scaffold-v0` tag and push; connect Cloud Build
- **Owner / model:** COORD + OWNER (permission and GitHub-app click) · Sonnet
- **Inputs:** owner's go-ahead ("push"); remote `https://github.com/Rammanobi/care_memory.git`
- **Touches:** git history; GitHub; Cloud Build trigger
- **STEPS**
  1. Run `git add -A && git status --short`. Confirm that `.env`, `node_modules/` and `.venv/` are **not** listed.
  2. Commit with `git commit -m "L0: scaffold baseline (pre-contracts)"`, then `git tag scaffold-v0`.
  3. Owner says "push". COORD runs `git push -u origin main --tags`.
  4. Owner installs the Cloud Build GitHub app in the console, and creates a trigger on `main` → `infra/cloudbuild.yaml`. Leave the trigger disabled until H6 if the YAML is not ready.
  5. Do **not** create `contracts-v1` tonight. That tag marks the frozen tier-1 contracts at H2:30.
- **Deliverable:** a pushed baseline
- **Done when:** `git ls-remote origin` shows `main` and `scaffold-v0`; `git ls-files | grep -E '^\.env$'` is empty
- **Effort:** 0.2 h

#### 0.10 Organiser check (the one call that could change the plan)
- **Owner / model:** OWNER · none
- **Inputs:** the organiser contacts in PREFLIGHT A1 #1
- **Touches:** `OPS_LOG.md` → Decisions
- **STEPS**
  1. Call or WhatsApp the desk and ask, word for word: "May we bring architecture documents and an empty repo skeleton, with all code written during the 36 hours?" Get the answer in writing.
  2. Ask for:
     - the official H0;
     - the times of the idea, prototype and final rounds;
     - the length of the final demo slot and of the Q&A;
     - the submission format (GitHub link, video, PPT; whether the repo must be public);
     - the deadline.
  3. Ask whether the Day-1 list matches the draft catalogue, and whether Open Innovation (IC26-03-10) is allowed.
  4. Book 2 HealthTech mentor slots in H6–H10, and send each mentor the one-pager.
  5. Write every answer verbatim into `OPS_LOG.md`.
- **Deliverable:** written organiser answers
- **Done when:** the `OPS_LOG.md` Decisions section has an "Organiser:" entry with a timestamp
- **Effort:** 0.2 h

#### 0.11 Roles, sleep plan, standing commit permission, demo kit
- **Owner / model:** OWNER · none
- **Inputs:** team headcount
- **Touches:** `OPS_LOG.md` → Roster
- **STEPS**
  1. Fix the four demo roles:
     - **Speaker:** never touches the laptop.
     - **Driver:** reset, slider, dashboard.
     - **"Doctor":** approves on cue, from the second phone.
     - **Backup:** hot-spare laptop and the video.

     With 3 people, the backup plays the doctor and the owner speaks.
  2. Fix the sleep shifts: owner and speaker H12–H18; driver and backup H20–H24; everyone awake from H26.
  3. Give **standing permission** in chat: lane agents may commit to their own `lane/*` branches; only the coordinator merges to `main`; pushes still need the owner's "push".
  4. Speaker and owner read the 10-page explainer PDF tonight.
  5. Pack: laptops, chargers, 2 power strips, an HDMI/USB-C adapter, a hotspot phone with at least 10 GB of data, a second SIM on another carrier, the 3 demo phones, college IDs and the A5 QR print.
- **Deliverable:** roster and permission recorded
- **Done when:** the `OPS_LOG.md` Roster names all four roles, and the permission line is quoted
- **Effort:** 0.25 h

#### 0.12 Problem-statement pre-mapping and pitch hygiene
- **Owner / model:** COORD · Sonnet
- **Inputs:** `ps.txt` (draft catalogue), `CAREMEMORY_STORY_AND_FEATURES.md`, the IDD never-cut list
- **Touches:** `caremem/docs/PS_MAPPING_DRAFTS.md`; `PITCH_PLAN.md` (name fix)
- **STEPS**
  1. Draft three mapping tables, one each for MedAdhere 03-02, CareRoute 03-01 and Open 03-10. Each maps: expected output → our feature → demo beat → assumption or limit.
  2. Write the "must not replace clinical diagnosis" safety paragraph once, and reuse it in all three.
  3. Replace "SaathiLoop" with "CareMemory" in `PITCH_PLAN.md` and any slide.
  4. Check that the `problem.html` statistics have their sources listed (MoHFW 26.18 lakh, ~25% of global cases, 99DOTS 21%, 62% nutrition payments, Lancet 2025).
- **Deliverable:** the H0 decision becomes a 10-minute pick
- **Done when:** `PS_MAPPING_DRAFTS.md` has three complete tables with no empty cell; `grep -rn SaathiLoop caremem_deck PITCH_PLAN.md` is empty
- **Effort:** 0.4 h

#### 0.13 Pre-freeze RFC pack for Opus (twin accounts and UI P0 needs)
- **Owner / model:** COORD · Sonnet (draft only; Opus decides at H0:30)
- **Inputs:** `TWIN_ACCOUNT_DEMO_PLAYBOOK.md` §3; `UI_FEATURES_RESEARCH.md` §A
- **Touches:** `caremem/contracts/CHANGES.md` (draft entries marked `PROPOSED`)
- **STEPS**
  1. Write the 9 twin-account changes as RFC entries:
     - `clinics.sim_day`, `clinics.day0_date`;
     - `current_sim_day(clinic_id)`;
     - `clinic_id` on `TaskEnvelope`;
     - per-clinic nightly and sweeper;
     - the scoped accounts;
     - the Compare page;
     - the `DEMO_MODE` banner.
  2. Write UI RFCs only where a contract field is needed:
     - `TrustLine.coverage_label` for the uncertainty label;
     - a per-source `last_recorded_at` in `PatientDetail` for the freshness chips;
     - `FlagChip.why{threshold, observed, clears_when}` for the why-this-flag popover.
  3. Mark everything else in the UI research as frontend-only, with no contract change.
- **Deliverable:** a ready list Opus can accept in about 10 minutes
- **Done when:** `CHANGES.md` has 12 `PROPOSED` entries, each with a fallback
- **Effort:** 0.3 h

### Parallelism map (Phase 0)
- **Start first:** 0.2, because the SQL create is the long pole.
- **While SQL builds:** 0.1, 0.3, 0.4, 0.5 (owner) run alongside 0.7, 0.12, 0.13 (COORD).
- **0.6** needs the secret values from 0.3, 0.4 and 0.5.
- **0.8** needs 0.2 finished and 0.6 done.
- **0.9** can run any time after 0.7. 0.10 and 0.11 are owner-only and can run at any point.
- **Short-time order:** 0.1–0.3, 0.9, 0.10, 0.11 are the owner-only blockers. COORD can finish 0.6, 0.7, 0.8 and 0.13 during H0–H2:30 tomorrow.

### Phase 0 exit gate
- [ ] `git tag -l scaffold-v0` prints the tag; `git ls-remote origin` shows `main`; no `.env` is tracked.
- [ ] `curl <cm-api>/healthz` and `/readyz` return 200 on run.app.
- [ ] The pgvector version is recorded (≥ 0.7, or the `RAG_VECTOR_TYPE=vector` flag is set).
- [ ] Secrets are all present (`gcloud secrets list`); spend caps are visible in the dashboards; no `<...-model>` placeholder remains.
- [ ] `pip check` is clean; the compose DB is healthy; `npx openspec validate --all` runs.
- [ ] The organiser answer, the roster and the standing commit permission are in `OPS_LOG.md`.

### Risks and recovery
| Risk | Recovery |
|---|---|
| The Cloud SQL create fails or hangs | Confirm `--edition=ENTERPRISE` and retry once. If it is still stuck, build locally tomorrow on compose and retry at H1 while L0 freezes the contracts |
| Gmail OAuth consent is blocked | Run the M lane on the simulated inbox. Log cut #9 as a pre-authorised contingency |
| A pin does not resolve | Use the latest version on the same major. Never cross a major version tonight |
| The organisers ban pre-built work | "Documents allowed, all code on the floor": the scaffold is stubs, so delete them. If documents are banned too, rebuild the plan around the never-cut list only (about a 30% scope cut) |
| The owner runs out of time | Stop after the blocker set (0.1–0.3, 0.9–0.11); COORD finishes the rest from H0 |

### Owner actions (Phase 0)
1. Console clicks: billing, budget alerts, OAuth consent, the Cloud Build GitHub app.
2. Create the keys and paste them into gcloud prompts (never chat); set the spend caps; pick the exact model IDs.
3. Create both Telegram bots; log in the three phones.
4. Call the organisers; book the mentors.
5. Fix the roster and sleep plan; give the standing commit permission; say "push" for the baseline.
6. Read the explainer; pack the kit.

---

# Phase 1: Kickoff, problem-statement lock and go/no-go (H0 → H0:30 = 10:00–10:30)

**Phase goal.**
- Pick the official Day-1 problem statement CareMemory answers, and write a mapping with no expected output left unmapped.
- Start the L0 contract freeze within 10 minutes of H0 (the contracts do not depend on which statement we pick).
- Get the owner's go-ahead on the pre-accepted cuts and the agent cap.

**Hours:** 0.5 h wall clock. Opus starts here (first Opus message at H0).

### Tasks

#### 1.1 Lock the problem statement and write `docs/PS_MAPPING.md`
- **Owner / model:** COORD · Opus
- **Inputs:** the official statement list; `PS_MAPPING_DRAFTS.md` (0.12); the IDD never-cut list
- **Touches:** `caremem/docs/PS_MAPPING.md`
- **STEPS**
  1. Read the official list and score MedAdhere 03-02, CareRoute 03-01 and Open 03-10 against our features.
  2. Pick one ID. The default is 03-02 if offered; 03-10 is the safety net.
  3. Copy the matching draft table, then fill every official "expected output" with: our feature → demo beat → assumption or limit.
  4. Add an explicit "Safety and limits" block: the AI does not diagnose, a doctor approves every outbound AI message, mock data only, an honest misses list.
  5. Open the OpenSpec change `add-ps-mapping` (doc-only, `--skip-specs`) and archive it.
- **Deliverable:** a one-page mapping
- **Done when:** the file names one statement ID, and `grep -c "| — |" docs/PS_MAPPING.md` returns 0 (no unmapped row)
- **Effort:** 0.35 h

#### 1.2 Spawn the L0 Contracts agent
- **Owner / model:** COORD · Opus (spawns an Opus agent)
- **Inputs:** the agent brief template (PHASES_SCRIPT); the IDD hour-0 checklist rows H0:15 → H2:30; the RFC pack (0.13)
- **Touches:** none directly (L0 works on `main`)
- **STEPS**
  1. Fill the brief: lane L0, the owned paths from IDD §e, the checklist rows as the task list, and the instruction "commit after every checklist row".
  2. Add: "Decide the 12 `PROPOSED` RFCs in `contracts/CHANGES.md` before writing `domain.py`."
  3. Spawn it, and record the agent ID in `OPS_LOG.md`.
- **Deliverable:** L0 running
- **Done when:** L0 reports its first commit on `main` (lanes.yaml + scaffold dirs)
- **Effort:** 0.05 h

#### 1.3 Spawn the I Infra agent for the Phase 0 leftovers
- **Owner / model:** COORD → I · Haiku
- **Inputs:** the blocker list in `OPS_LOG.md`; spec 04 F8 and F9
- **Touches:** `infra/`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `scripts/` (except L0's)
- **STEPS**
  1. Brief I with every unfinished Phase 0 item (0.6, 0.8 if they are open) and task 2.6.
  2. Tell it the RPM tier, so queue sizing matches.
  3. Spawn it in the main checkout until worktrees exist (H2:30), then move it to `../cm-i-infra`.
- **Deliverable:** I running
- **Done when:** I reports a dry run of `infra/60_deploy.sh`
- **Effort:** 0.05 h

#### 1.4 Confirm round times and demo length; re-base the clock
- **Owner / model:** OWNER · none; COORD records
- **Inputs:** the organisers' desk
- **Touches:** `OPS_LOG.md`; the "Round readiness" times in PHASES_SCRIPT
- **STEPS**
  1. Get the idea, prototype and final round times, the demo length and the Q&A length.
  2. If the real H0 is not 10:00, COORD re-bases every wall-clock time in `OPS_LOG.md`.
  3. If the demo slot is not 3:00, flag "re-time beats" for task 8.6.
- **Deliverable:** confirmed schedule
- **Done when:** the `OPS_LOG.md` Clock section shows the confirmed times, or "unknown, chase at H2"
- **Effort:** 0.1 h

#### 1.5 Go/no-go: pre-accepted cuts, agent cap, morning decisions
- **Owner / model:** OWNER decides · COORD presents (Opus)
- **Inputs:** PREFLIGHT §C decisions 1–15
- **Touches:** `OPS_LOG.md` → Decisions
- **STEPS**
  1. COORD presents, in one message:
     - the statement pick;
     - the model split (orchestrator, vision and embedding on OpenAI; worker and judge on DeepSeek);
     - **pre-accepting cuts 1 and 2** (IDD §g);
     - an 11-agent peak cap;
     - the doctor role, the judge-seed plan and the business line.
  2. The owner answers approve, approve-with-changes, or skip.
  3. COORD records each answer verbatim.
  4. If cuts 1 and 2 are accepted, open `remove-channel-kill-switches-whatif` and `remove-timeline-lanes-tab` (REMOVED deltas). Each IDD "replaces on stage" line goes into the `docs/DEMO_SCRIPT.md` stub.
- **Deliverable:** go decision
- **Done when:** `OPS_LOG.md` shows "GO" with a timestamp and the cut decisions
- **Effort:** 0.1 h

### Parallelism map (Phase 1)
- 1.2 and 1.3 are spawned in the first 10 minutes and do **not** wait for 1.1.
- 1.1 and 1.4 run in parallel.
- 1.5 waits for 1.1 (it needs the statement ID).

### Phase 1 exit gate
- [ ] `docs/PS_MAPPING.md` names one ID with every expected output mapped.
- [ ] L0 has committed on `main`; I is running.
- [ ] Round times and the demo length are recorded (or flagged to chase at H2).
- [ ] The go decision, cuts 1–2 and the agent cap are recorded.

### Risks and recovery
| Risk | Recovery |
|---|---|
| No statement fits | Take Open 03-10, which lets us define our own title; the design stays whole |
| A statement demands a feature we have not designed | Map it to an existing P1 item (Patient PWA) or the Telegram flow, and say so in the mapping. Add no P0 scope |
| Opus is capped at H0 | L0 runs on Sonnet with a strict brief; Opus reviews the diff before the `contracts-v1` tag |
| The organisers ban pre-built design at registration | Delete the scaffold stubs, keep the documents, and tell the owner at once; re-plan around the never-cut list |

### Owner actions (Phase 1)
1. Answer the statement pick and the go/no-go (about 10 minutes).
2. Get the round times and demo length from the desk (or send a teammate).
3. Approve cuts 1–2 and the 11-agent cap.

---

# Phase 2: Contract freeze, `contracts-v1` (H0:30 → H2:30 = 10:30–12:30)

**Phase goal.** Tier-1 contracts, the `0001_core` migration, `docs/maths.md`, `docs/generator.md` and the tier-1 golden fixtures are frozen and tagged `contracts-v1`. The 14 lane worktrees exist, and the ownership hook rejects out-of-lane edits.

**Hours:** 2 h. Only 2 agents run, on purpose: one Opus (L0) and one Haiku (I).

### Tasks

#### 2.1 Scaffold the lanes and the ownership hook; update `CLAUDE.md`
- **Owner / model:** L0 · Opus
- **Inputs:** IDD §e lane table; `caremem/CLAUDE.md`
- **Touches:** `scripts/lanes.yaml`, `scripts/check_ownership.py`, `.pre-commit-config.yaml`, `CLAUDE.md`, directory stubs (`__init__.py`, `NOTES.md` per lane)
- **STEPS**
  1. Write `scripts/lanes.yaml`, one entry per lane with its exclusive globs, copied from the IDD §e table.
  2. Have `check_ownership.py` read the branch name (`lane/<x>`) and reject any staged path outside that lane's globs. `main` is allowed only for L0 and INT.
  3. Install it as a pre-commit hook.
  4. Create every lane directory with a `NOTES.md` that holds an empty `RESUME POINT` block.
  5. Update `CLAUDE.md`:
     - 14 lanes;
     - `task_runs`, `approval_id`, `recorded_at`;
     - OpenAI/DeepSeek only;
     - `cm/review/decide.py` is the only decision path;
     - citation refs E/B/C/R/G/D.
  6. Commit: `L0: lanes scaffold + ownership hook`.
- **Deliverable:** lane fences
- **Done when:** `python scripts/check_ownership.py --self-test` passes
- **Effort:** 0.3 h

#### 2.2 Decide the pre-freeze RFCs
- **Owner / model:** L0 · Opus
- **Inputs:** `contracts/CHANGES.md` `PROPOSED` entries (0.13); TWIN_ACCOUNT §3
- **Touches:** `contracts/CHANGES.md`
- **STEPS**
  1. Accept the twin RFCs that cost nothing if unused:
     - `clinics.sim_day int NULL`, `clinics.day0_date date NULL`;
     - `TaskEnvelope.clinic_id`;
     - `current_sim_day(clinic_id=None)` behaviour, documented for lane A.
  2. Accept the UI fields `FlagChip.why`, `TrustLine.coverage_label` and the per-source `PatientDetail.freshness`, all optional and nullable.
  3. Reject anything that renames an IDD name.
  4. Mark each entry ACCEPTED, MODIFIED or REJECTED, with its owner lane.
- **Deliverable:** a decided RFC list
- **Done when:** no `PROPOSED` remains in `CHANGES.md`
- **Effort:** 0.15 h

#### 2.3 Write the tier-1 contracts
- **Owner / model:** L0 · Opus
- **Inputs:** IDD §a (E1–E8, T1–T20, K1–K5, M1–M11, P1–P9), §d
- **Touches:** `cm/contracts/{domain,memory,review,agents,api,tools}.py`
- **STEPS**
  1. `domain.py`: the shared `Literal` aliases (`Role`, `Tier`, `ReporterMode`, `DoseStatus`, `ConsentSource`, `Purpose`, `OutboundChannel`, `AgeBand`) and the full 21-member `Event` discriminated union on `type`, including `CheckinPrompt`, `RegimenChange`, `ChannelUnreachable`, `PortalRegistration`, `HouseholdContactEvent` and `ConsentEvent`.
  2. `memory.py`:
     - `RiskScore` with `p_miss7` and its CI;
     - `Belief`, `Conflict` (rule R1–R6), `MemorySnapshot`, `LensComparison`, `FunnelSeries`, `TrustLine`, `Coverage`;
     - `EvidenceBundle`, `NarrationDraft`, `MemoryCard`, `Sentence`, `ValidatorReport`;
     - `InMemoryResult` as a frozen dataclass.
  3. `review.py`:
     - `ReviewKind` (the 10 kinds from K1);
     - `ProposalOut` with `recipients`, `ReviewQueueOut`, `ReviewDecisionIn`, `ExpiredDecision`, `ReviewDecisionOut` (`via` includes `sweeper`);
     - `BulkDecisionIn{approval_ids, viewed_approval_ids}`;
     - `DigestItem`, `ReplyCommand`, `ReplyParse`.
  4. `agents.py`: `TaskEnvelope` (+ `clinic_id`), `ResumeEnvelope`, `ToolContext`, `RawInbound`, `ParsedInbound` (no `FreeTextNote`), `IdentityQuery`, `IdentityMatch`, `QueryIn`, `QueryAnswer`, `JudgeVerdict`, `TokenMap`, `InjectionScan`.
  5. `api.py`: `Problem`, `Page[T]`, `LiveEvent`, the ingest models, `HouseholdContactIn/Out`, `TelegramUpdate`, `TgCallback`, `PubSubPush`, `ChannelProfile`, `VisitList`.
  6. `tools.py`: the 19 `runtime_checkable` Protocols from IDD §d.
  7. Configure Pydantic v2 strict mode everywhere. Commit after each file.
- **Deliverable:** tier-1 contracts
- **Done when:** `python -c "import cm.contracts.domain, cm.contracts.memory, cm.contracts.review, cm.contracts.agents, cm.contracts.api, cm.contracts.tools"` exits 0, and `pytest tests/contracts -q` is green
- **Effort:** 1.0 h

#### 2.4 Write the `0001_core` migration
- **Owner / model:** L0 · Opus
- **Inputs:** IDD §b
- **Touches:** `cm/store/migrations/versions/0001_core.py`, `alembic.ini`
- **STEPS**
  1. Create every §b table except the RAG pair. Include `clinics.sim_day` and `clinics.day0_date` (2.2).
  2. Add every UNIQUE and CHECK constraint:
     - `events.idempotency_key`;
     - `approvals (thread_id, interrupt_id)`;
     - `review_decisions.approval_id`;
     - `outbox.dedup_key`;
     - the outbox CHECK (`decision_id` or `template_id`);
     - `erasure_requests` `approved_by <> requested_by`;
     - `eval_runs` UNIQUE.
  3. Add stub INSERT-only triggers for `events` and `audit_log`, and a stub approved-template trigger on `outbox`. Lane A completes them in 0003.
  4. Add the indexes: `events (patient_id, occurred_at)` and `(patient_id, recorded_at)`.
  5. Run `make up migrate` against compose Postgres.
- **Deliverable:** the schema as the contract
- **Done when:** `make contracts-check` is green, and `alembic upgrade head` exits 0 on compose
- **Effort:** 0.5 h

#### 2.5 Freeze `docs/maths.md` and `docs/generator.md`
- **Owner / model:** L0 · Opus
- **Inputs:** spec 02 F4/F5 maths, IDD M5 labels, spec 04 F1 pattern table and Ravi overlay
- **Touches:** `docs/maths.md`, `docs/generator.md`
- **STEPS**
  1. `maths.md` holds the frozen parameters:
     - priors: weekday `Beta(1,9)` with κ=4; trust `Beta(8,2)`, `(6,2)`, `(19,1)`;
     - thresholds: hypothesis/confirm 0.60/0.90; CUSUM k=0.5, h=4;
     - the lifecycle timings;
     - R1–R6 parameters, including `contacts_due_day=14`;
     - labels `miss7` and `dropout14`;
     - seed ranges: train 1000–1099, calibrate 1100–1149, evaluate ≥2000; demo 42 flagged.
  2. Compute `frozen_spec_hash` (sha256 of `maths.md`) and record it.
  3. `generator.md` holds:
     - pattern marginals and conditional rates;
     - the opt-in mixes;
     - the noise rates;
     - the Ravi overlay table: Thu 6/8, trust 0.41, refill due 28 / bought 44 with 16 taps, reply time 9→85 min, 7 unknowns on day 3 and 2 on day 60;
     - Ravi's household: Sunitha (spouse, 15–59, no symptoms), Meena (child, 5–14, night cough), son (under 5).
- **Deliverable:** frozen maths and generator specs
- **Done when:** `frozen_spec_hash` is printed in `maths.md`, and `generator.md` contains the Ravi table and household
- **Effort:** 0.25 h

#### 2.6 Infra skeleton for H6 (runs through Phases 2 and 3)
- **Owner / model:** I · Haiku
- **Inputs:** spec 04 F8 and F9; IDD a6
- **Touches:** `infra/60_deploy.sh`, `infra/cloudbuild.yaml`, `infra/70_scheduler.sh`, `infra/80_webhooks.sh`, `Dockerfile`, `docker-compose.yml`, `.env.example`
- **STEPS**
  1. `Dockerfile`: one image, two entry points (`cm-api`, `cm-worker`), with `CM_ROLE` selecting the app. Uvicorn is run programmatically (needed for the SIGTERM hook in 4.1).
  2. `60_deploy.sh`: deploy `cm-api` (public, `min-instances=1`, 60 s timeout) and `cm-worker` (private, OIDC, 1800 s timeout). Create the jobs `cm-migrate`, `cm-seed`, `cm-nightly`, `cm-sweeper` and `cm-eval`.
  3. `cloudbuild.yaml`: build → run `cm-migrate` (600 s) → deploy. Wire the trigger on `main`.
  4. `docker-compose.yml`: db (`pgvector/pgvector:pg16`), api on 8080, worker on 8081, web on 5173. Add `DEMO_MODE=0` and the `CM_OFFLINE` profile to `.env.example`.
  5. Dry-run `60_deploy.sh` with `--dry-run`.
- **Deliverable:** a deployable skeleton
- **Done when:** `bash infra/60_deploy.sh --dry-run` prints every gcloud command with no unset variables, and `docker compose config` validates
- **Effort:** 2.0 h

#### 2.7 Write the tier-1 golden fixtures
- **Owner / model:** L0 · Opus
- **Inputs:** 2.3 contracts, 2.5 maths and generator specs
- **Touches:** `fixtures/*.json`, `fixtures/seed42_events_sample.jsonl`, `fixtures/channels/household_ravi.json`, `fixtures/channels/visit_list_approved_d60.json`
- **STEPS**
  1. `MemorySnapshot_ravi_d3`: risk `0.12 [0.04–0.35]`, "too little data", 7 unknowns. `MemorySnapshot_ravi_d60`: risk `0.58 [0.44–0.71]`, the Thursday belief ≈0.97, trust 0.41, R1 closed on day 44, R3 open, R6 closed, 2 unknowns. Every sentence carries E/B/C/R refs.
  2. `LensComparison_ravi_3_60` and `FunnelSeries_ravi` (CI width narrowing from day 3 to day 60).
  3. `ReviewQueueOut_demo` with exactly 1 Red, 6 Amber and 23 Green. Also `ReviewItemDetail_ravi_card_d60` and `ReviewItemDetail_kavya_red`.
  4. `PatientSummary_list_clinic`, `PatientDetail_ravi_d60`, `TimelineItem_list_ravi`, `EventOut_chemist_csv_d44`, `TaskEnvelope_*`.
  5. `household_ravi.json`, `visit_list_approved_d60.json` and the 10-line `seed42_events_sample.jsonl`.
  6. Check every fixture parses in strict mode.
- **Deliverable:** the shared golden truth every lane builds against
- **Done when:** `make contracts-check` parses every fixture strictly (0 failures)
- **Effort:** 0.5 h

#### 2.8 Tag `contracts-v1`, create the worktrees, test-fire the hook
- **Owner / model:** COORD · Opus
- **Inputs:** 2.1–2.7 committed
- **Touches:** git tags, `../cm-<lane>` worktrees
- **STEPS**
  1. Run `make contracts-check`, then `git tag contracts-v1`. Push the tag once the owner has approved pushes.
  2. Create the worktrees: `for lane in a-data b-sim c-memory d-rules e-runtime n-narration f-telegram m-gmail g-api h1-doctor h2-district i-infra j-eval k-content; do git worktree add ../cm-$lane -b lane/$lane contracts-v1; done`.
  3. From `../cm-a-data`, edit a file in `cm/contracts/` and attempt a commit. Expect the hook to reject it, then revert.
  4. Archive `add-contracts-v1` (with spec deltas per capability).
- **Deliverable:** 14 isolated build lanes
- **Done when:** `git worktree list` shows 15 entries; `git tag -l contracts-v1` prints it; the forged commit was rejected
- **Effort:** 0.15 h

### Parallelism map (Phase 2)
- **L0 runs serially:** 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.7 → 2.8. 2.4 and 2.5 may swap.
- **I (2.6)** runs fully in parallel with no dependency.
- **COORD**, while L0 works, finishes any open Phase 0 items (0.6–0.8, 0.13) and pre-writes the 14 lane briefs for H2:30, ready to paste.

### Phase 2 exit gate
- [ ] `contracts-v1` exists; `make contracts-check` is green.
- [ ] `0001_core` migrates on compose (`make up migrate` exits 0).
- [ ] The Ravi fixtures: day 3 shows "risk unknown, too little data"; day 60 shows HIGH with at least 3 cited beliefs.
- [ ] 15 worktrees exist, and the ownership hook rejects an out-of-lane edit.
- [ ] `npx openspec list --json` shows `add-contracts-v1` archived.

### Risks and recovery
| Risk | Recovery |
|---|---|
| L0 is not done by H2:30 | Tag whatever tier-1 work is complete by H2:45 at the latest; missing models move to `contracts-v1.1` at H4. Lanes without their contract start on fixture-only tasks |
| Opus caps mid-freeze | L0 committed after each row, so a Sonnet agent resumes from `git log` plus the `cm/contracts/NOTES.md` RESUME POINT. Opus reviews the diff before the tag |
| `0001_core` fails on Postgres | Fix it inside L0 now. This is the only time a migration bug is cheap |

### Owner actions (Phase 2)
1. Nothing to build. Book the mentor slots if not done, test the venue Wi-Fi and Telegram reachability, and test the hotspot.
2. Approve pushing the `contracts-v1` tag, if pushes are not already standing.

---

# Phase 3: Wave 1 build, tier-2 freeze and Integration 1 (H2:30 → H6 = 12:30–16:00)

**Phase goal.**
- The foundations are coded against fakes, in 13 lanes.
- Tier-2 contracts and `openapi.json` are frozen at H4 (`contracts-v1.1`).
- Prompts and playbooks exist by H6.
- At H6, Integration 1 merges A (core slice), B (generator), D (rules) and K (content).
- The seed runs on Cloud SQL, and a skeleton `cm-api`/`cm-worker` is deployed.
- The idea-round deck is ready, because the idea round probably falls at H4–H8.

**Hours:** 3.5 h. The agent peak is 11 (8 at H2:30, plus C, E and N at H3; H2 joins at H4 if the usage meter is below 60%).

### Tasks

#### 3.1 A: core runtime modules
- **Owner / model:** A · Sonnet
- **Inputs:** `contracts-v1`; spec 04 F4/F5/F6; IDD C21 (id formats); twin RFC (clinic clock)
- **Touches:** `cm/core/{config,clock,ids,tasks,local_queue,llm,retry,tokenize,logging,lifecycle,db}.py`, `cm/core/fakes.py`
- **STEPS**
  1. `config.py`: pydantic-settings for every `.env.example` name; `DEMO_MODE`, `CM_OFFLINE`, `TASKS_MODE`, `CM_DATA_CLASS`.
  2. `clock.py`:
     - `now()`, `today()` and `current_sim_day(clinic_id=None)`;
     - the clinic's pinned `sim_day` wins, else the global `sim_clock`;
     - `end_of_sim_day(d)` in IST;
     - no `datetime.now()` anywhere else.
  3. `ids.py`: the colon-free `task_id` builders, plus `thread_id`, `dedup_key` and the event key formats (IDD C20, C21, C23).
  4. `tasks.py`: `enqueue(queue, task_id, path, body, schedule_time)` with Cloud Tasks and OIDC, treating `AlreadyExists` as False. `local_queue.py`: an asyncio queue per name with named dedupe and backoff, for `TASKS_MODE=local`.
  5. `llm.py`:
     - `get_model(key)` via `init_chat_model`, using the per-key rate limiter, `max_retries`, the 60k token budget callback and `ModelFallbackMiddleware`;
     - refuse `deepseek:` when `CM_DATA_CLASS=real`;
     - the `OFFLINE` key returns the cassette model (stub until J lands);
     - `assert_clean()` on prompts.
  6. `retry.py`: retry 429, 5xx and timeouts, honouring `retry_after`; **never** retry spend-cap or auth errors. Add an `error_class` classifier.
  7. `tokenize.py`, `logging.py` (JSON, no PII) and `lifecycle.py` (the `shutting_down` flag, `CMServer.handle_exit`).
  8. Write the fakes for `Clock`, `TaskQueue` and `ModelFactory`.
- **Deliverable:** the runtime base every lane imports
- **Done when:** `pytest tests/core -q` is green, including:
  - `test_task_id_has_no_colon`;
  - `test_retry_never_retries_spend_cap`;
  - `test_clinic_pinned_day_overrides_global`;
  - `test_assert_clean_rejects_phone`.
- **Effort:** 2.5 h

#### 3.2 A: event store and repositories (core slice by H7)
- **Owner / model:** A · Sonnet
- **Inputs:** `0001_core`; spec 02 F3; IDD M2, K2 and T1–T3
- **Touches:** `cm/store/{events_repo,as_of,consent,task_runs_repo,approvals_repo,outbox_repo,settings_repo,household_repo}.py`, `cm/store/fakes.py`
- **STEPS**
  1. `events_repo.append_event(e, ctx)`:
     - check consent first; no active consent means drop and audit;
     - `INSERT … ON CONFLICT (idempotency_key) DO NOTHING RETURNING`, else select the existing row;
     - run a post-commit `fast_path` hook (a no-op until D lands).
  2. `bulk_append(events)` via COPY into a temp table, then `INSERT … ON CONFLICT`, for B's seed. **Ship it first**, because B needs it.
  3. `as_of.query(pid, as_of, types, window)`: a CTE with `occurred_at ≤ T AND recorded_at ≤ T`, the latest non-superseded version, and currently-withdrawn sources dropped. Also the pure `filter_as_of(events_df, as_of_day, consents_df)` (M2).
  4. `consent.effective(person, source, purpose, as_of)` using `DISTINCT ON`.
  5. The `task_runs` repo: insert ON CONFLICT DO NOTHING, the atomic claim `UPDATE … RETURNING`, heartbeat and `set_state`.
  6. The `approvals` repo: upsert on `(thread_id, interrupt_id)`; `queue()` joining `due_at` and `sample_reason`; `FOR UPDATE` load.
  7. The `outbox` repo: upsert on `dedup_key`; the drainer claim with `FOR UPDATE SKIP LOCKED LIMIT 20`.
  8. The `settings` repo (60 s cache, optimistic `version`) and the `household` repo (projection upsert). Write a fake for each Protocol.
- **Deliverable:** the only read and write paths to the database
- **Done when:** `pytest tests/store -q` is green, including:
  - double append is idempotent;
  - an UPDATE on `events` raises;
  - `query(as_of=44)` excludes a dispense recorded on day 46;
  - a withdrawal removes events from the day-3 replay;
  - the property test `filter_as_of` == `query`.
- **Effort:** 3.0 h (ends at H7, crossing into Phase 4)

#### 3.3 B: synthetic world generator and the H5 fixture drop
- **Owner / model:** B · Sonnet
- **Inputs:** `docs/generator.md`; spec 04 F1 steps 1–14; IDD E2 (`RegimenChange`), E5 (household), T16 (Ni-kshay)
- **Touches:** `cm/sim/{params,rng,patterns,doses,reports,supporter,noise,household,nikshay,ravi,writer}.py`, `fixtures/sim/seed42/`
- **STEPS**
  1. RNG tree: `SeedSequence(seed).spawn(n)`, with 7 streams per patient. No global RNG, no set iteration, sorted keys.
  2. Pattern assignment: `no_pattern` 20%, then the conditional flags (market day, payday, over-reporter, drift, payment failure), plus R2 and R4 plants at 3% each.
  3. Stock-gated true doses (28-tablet packs, geometric refill delay). Test the invariant `cumsum(taken) ≤ cumsum(dispensed)`.
  4. Self-reports, with `CheckinPrompt` at 07:30 and the reply-time lognormal; Supporter visits (witnessed, told, unreachable) and pill counts; weight, symptoms, labs and payments; a `RegimenChange` at treatment start for every patient.
  5. Household members per patient (age bands, symptom draws) as `HouseholdContactEvent`s. Ni-kshay mock rows with 15% failures. Channel opt-in mixes with their `ConsentEvent`s. Noise: CSV lag 1–3 days, 5% misspellings, 1% duplicates.
  6. The Ravi overlay (`ravi.py`) pins every value in the design table, including the household (Sunitha, Meena, son), and flags him `scripted`.
  7. Write `events.jsonl`, the CSVs and `manifest.json`. Write `truth.json` to `TRUTH_DIR` only.
  8. **H5 fixture drop:** commit the `fixtures/sim/seed42/` events and the Ravi overlay, and send C the message "real data ready".
- **Deliverable:** a deterministic 40-patient world with planted truth
- **Done when:** `pytest tests/sim -q` is green, including `test_same_seed_same_sha`, `test_refill_invariant`, `test_ravi_overlay_targets` and `test_truth_not_importable_outside_eval`
- **Effort:** 3.0 h

#### 3.4 D: rules R1–R6, `reconcile_frame` and the fast path
- **Owner / model:** D · Sonnet
- **Inputs:** spec 02 F6; IDD M3 and M8 (R6); `docs/maths.md`
- **Touches:** `cm/rules/{rules_r1..r6,reconcile,fast_path,supply_ledger,ids}.py`, `cm/rules/fakes.py`
- **STEPS**
  1. `supply_ledger(events, as_of)`: `on_hand(d) = Σ dispensed − daily_dose × days`, with a 3-day lag guard.
  2. R1 (refill vs self-report, Amber), R2 (DR result vs latest `RegimenChange` as of the lab's `recorded_at`, **Red**), R3 (payment, Amber), R4 (danger symptom, **Red**), R5 (≥3 unanswered `CheckinPrompt`s with no Supporter contact; Amber, Red at 7).
  3. **R6 (P0):**
     - fires from `contacts_due_day` (14) when there are zero listed contacts, or any listed contact has `screened_at IS NULL`;
     - suppressed by `ContextNote{kind:"household_declined"}`;
     - Amber;
     - closes when everything is screened.
  4. `conflict_id = uuid5(pid|rule|anchor_event_id)`. `opened_as_of` is kept and `closed_as_of` is set when the condition clears. The summary text is a template.
  5. `reconcile_frame(events_df, patient, as_of, thresholds)` is the single implementation; `reconcile(pid, as_of)` = load + frame. `fast_path(event)` runs R2 and R4 only.
- **Deliverable:** deterministic contradiction flags
- **Done when:** `pytest tests/rules -q` is green, with positive, negative and edge fixtures per rule:
  - a dispense recorded 2 days late gives no R1;
  - Ravi R1 opens around day 31 and closes on day 44;
  - R6 fires on day 14 and closes after screening;
  - a declined household gives no R6.
- **Effort:** 2.5 h

#### 3.5 F: Telegram client, webhook path, binding and patient check-in
- **Owner / model:** F · Sonnet
- **Inputs:** spec 01 F1 steps 1–8, F11 onboarding; A's fakes
- **Touches:** `cm/channels/{telegram,tg_webhook,tg_patient,tg_keyboards,tg_callback,binding}.py`, `cm/router/{router,templates}.py`, `fixtures/channels/tg_*.json`
- **STEPS**
  1. `telegram.py`: the raw Bot API over `httpx.AsyncClient` (`sendMessage`, `editMessageReplyMarkup`, `editMessageText`, `setWebhook`), wrapped in `cm.core.retry`. **No python-telegram-bot.**
  2. `handle_telegram_update(update)`:
     - compare the secret header with `hmac.compare_digest`;
     - handle private chats only;
     - stamp `tapped_at = clock.now()` first;
     - **import no LangChain in this module tree.**
  3. `binding.py`: `/start <code>` binds the invite (pending → active, expiry). An unbound chat gets only the invitation message, and only a hashed audit row is stored.
  4. Onboarding: three itemised consent questions → `ConsentEventIn` (via the F11 interface; fake until M lands); then language; then check-in time.
  5. Callbacks:
     - `c:{p}:t|m|u` loads the outbox row and **requires `recipient_id` = the bound person**;
     - append `DoseCheckin` with `reply_seconds`, key `tg:{update_id}`; a change within 2 h supersedes, after that the answer is locked;
     - reply with the inline `answerCallbackQuery`;
     - insert the `ack_*` outbox row.
  6. The stateless symptom checklist (8-bit mask in `callback_data`): Done gives one `SymptomReport`, and danger items 6–8 trigger the R4 fast path → Red.
  7. Fan-out handler `/tasks/checkins {as_of, slot}`: insert `checkin_daily` outbox rows per the `ChannelProfile`, with the dedup key.
- **Deliverable:** the patient side of the Telegram loop (against fakes)
- **Done when:** `pytest tests/channels/test_tg_* -q` is green with `respx`. A taken tap gives one event with the correct `reply_seconds`; a forged button is rejected; a duplicate update is a no-op; a danger tap creates a Red approval; nothing is sent without a template.
- **Effort:** 3.5 h

#### 3.6 G: auth, every route stub, `openapi.json` by H4
- **Owner / model:** G · Sonnet
- **Inputs:** IDD §c (the endpoint list), P4 (JWT), P5 (queue envelope); spec 03 §8
- **Touches:** `cm/api/{main,deps,auth,problems}.py`, `cm/api/routers/{webhooks,ingest,tasks,patients,review,supporter,stream,auth,health}.py`
- **STEPS**
  1. `auth.py`:
     - HS256 JWT signed with `JWT_SIGNING_KEY`;
     - claims `{sub, role, person_id, clinic_id, district_id, tv, iat, exp, jti}`, TTL 480 min;
     - the `cm_session` cookie (HttpOnly, Secure, SameSite=Strict) **and** Bearer;
     - mutations need `X-CM-Client: web`;
     - passwords via `hashlib.scrypt`;
     - `tv` checked against `auth_credentials` (60 s cache);
     - login limited to 10/min per IP and 5/min per username.
  2. `deps.py`: `require_role(...)` and clinic/district scope checks; the twin-account clinic scope comes from the token's `clinic_id`.
  3. Stub **every** P0 route in IDD §c with the correct response model, each returning its fixture (`fixtures/*.json`), so H1 can generate a client.
  4. Webhook verification: the Telegram secret header and the Pub/Sub OIDC (`verify_oauth2_token`, email check). Worker routes require the OIDC invoker.
  5. `/healthz` and `/readyz` (DB `SELECT 1`). `Problem` responses with `code`.
  6. By H4, export `fixtures/openapi.json` to L0 for the tier-2 freeze.
- **Deliverable:** the full API surface on fixtures
- **Done when:** `python -m cm.api.export_openapi > /tmp/o.json` lists every IDD §c P0 path (checked by `tests/api/test_route_inventory.py`); `pytest tests/api/test_auth.py` is green (bad `tv` → 401, missing `X-CM-Client` → 403)
- **Effort:** 3.5 h

#### 3.7 H1: console shell, design tokens, fixtures, login, queue skeleton
- **Owner / model:** H1 · Sonnet
- **Inputs:** spec 03 §0 and §8; `UI_FEATURES_RESEARCH.md` §E; tier-1 fixtures
- **Touches:** `web/package.json`, `web/src/{main.tsx,router.tsx,api,auth,realtime,components,styles,mocks}`, `web/src/pages/{Login,ReviewQueue}/`
- **STEPS**
  1. Vite + React + TypeScript + Tailwind + shadcn/ui + TanStack Query + Recharts + Lucide.
  2. `styles/tokens.css`: the colour-blind-safe light and dark palette (UI #13). The tier style is icon ▲ ● ✓ + word + a 4 px left-border pattern. The focus ring is overridden to 3 px at 3:1 contrast.
  3. App shell: the **"SYNTHETIC DATA, NOT REAL PATIENTS" banner** (UI #6) and the `DEMO_MODE` banner (twin #9); `MaskedId`; route guards per role; sim-day badge.
  4. MSW mocks serving every tier-1 fixture. After H4, generate the API client from `fixtures/openapi.json` (`openapi-typescript`).
  5. Login page: username/password, the cookie session, the `/auth/me` bootstrap.
  6. ReviewQueue skeleton on `ReviewQueueOut_demo`: lanes for Red, Amber and Green, with counts, and an `aria-live="polite"` region.
  7. Shared components: `TierBadge`, `RiskInterval`, `CitationChip`, `EventDrawer` (stub), `EmptyState`, `Skeleton`.
- **Deliverable:** a running console on fixtures
- **Done when:** `npm run build && npm run test` are green; on `npm run dev`, logging in as `doctor_demo` shows 1 Red / 6 Amber / 23 Green; the axe check on the queue page reports no violations
- **Effort:** 3.5 h

#### 3.8 K: templates, text bank, chemist CSV parser, Ni-kshay mock, RAG-lite seed
- **Owner / model:** K · Haiku
- **Inputs:** spec 01 F1/F3/F4/F7/F10/F13 template keys; IDD T6, T16
- **Touches:** `cm/router/templates/*.yaml`, `fixtures/text_bank.json`, `cm/channels/{chemist_csv,portal_mock}.py`, `cm/api/routers/mock_nikshay.py`, `cm/rag/`, `data/guidelines/`, `docs/{dpdp_notice_v1,breach_plan}.md`
- **STEPS**
  1. Write the EN templates for every key, each with slots and a tier:
     - patient: `checkin_daily`, `checkin_nudge`, `ack_taken`, `ack_missed`, `symptoms_check`, `danger_ack`, `payment_monthly`, `weight_monthly`, `stop_menu`, `mydata`, `clarify`;
     - Supporter: `visit_card`, `proxy_checkin`, `no_visits`;
     - doctor and family: `family_invite`, `doctor_digest`, `gmail_echo`, `chemist_receipt`;
     - system: `red_alert_doctor`, `red_alert_sts`;
     - calendar: `cal_refill`, `cal_test`, `cal_visit`, `cal_family_screen`;
     - `district_monthly`.
  2. Run `make banned-terms` over every template. The patient and Supporter strings contain no TB, tuberculosis, DOTS or drug names (EN, TE or HI).
  3. `fixtures/text_bank.json`: 40+ EN/TE/HI free-text messages tagged by intent (for B's generator and N's intake tests).
  4. `chemist_csv.parse`:
     - `utf-8-sig`, falling back to `cp1252`;
     - the header alias map;
     - limits of 2 MB / 5,000 rows;
     - row validation;
     - the key `chem:{chemist_id}:{bill_no}:{line_no}`, or `chem:{chemist_id}:sha1:{row_sha1}` without a bill number;
     - unknown headers → a `RawInbound`.
  5. The Ni-kshay mock router: `GET /mock/nikshay/patients/{id}`, `GET /mock/nikshay/payments?since`, and `POST /mock/nikshay/scenario` (admin). `MOCK_CHAOS` latency. `portal_mock.sync()` posts `PortalRegistrationIn` and `PortalPaymentIn`.
  6. RAG-lite: 15–25 guideline chunks in `data/guidelines/` with metadata; `cm/rag/seed.py` loads them into `documents` and `text_chunks` once 0004 exists.
  7. Write `docs/dpdp_notice_v1.md` (itemised, plain language) and `docs/breach_plan.md`.
- **Deliverable:** all content and the mock feeds
- **Done when:** `make banned-terms` is green; `pytest tests/channels/test_chemist_csv.py tests/channels/test_portal_mock.py -q` is green (misspelt header aliased; duplicate row reported; `pending → paid` gives 2 events)
- **Effort:** 3.5 h

#### 3.9 I: skeleton deploy, Cloud Build trigger, scheduler stubs
- **Owner / model:** I · Haiku
- **Inputs:** 2.6 output; the run.app URL
- **Touches:** `infra/*`
- **STEPS**
  1. Run `infra/60_deploy.sh` for real: `cm-api` and `cm-worker` from `main`, with secrets mounted per service.
  2. Enable the Cloud Build trigger, and push a no-op commit (coordinator-merged) to prove build → migrate → deploy.
  3. `infra/70_scheduler.sh`:
     - jobs created **paused**: 07:30 and 18:30 `/tasks/checkins`, 19:00 Supporter proxy, 00:30 `/tasks/portal-sync`, 01:00 `cm-nightly`, 12:00 `/tasks/digest`, 17:00 `/tasks/visit-lists`, 06:00 `/tasks/gmail-watch-renew`, `/tasks/gmail-sweep` every 30 min, `cm-sweeper` every 5 min;
     - IDD I7 (`run.invoker` on the jobs).
  4. Prepare `infra/80_webhooks.sh`, which runs once F's webhook is merged (task 4.14).
- **Deliverable:** a deploy pipeline and paused schedules
- **Done when:** `gcloud builds list --limit=1` shows SUCCESS; `gcloud scheduler jobs list` shows every job PAUSED
- **Effort:** 2.0 h

#### 3.10 C: feature builder L1 and the first detectors (starts H3)
- **Owner / model:** C · Sonnet (Opus maths)
- **Inputs:** spec 02 F4 and F5 A–C; `docs/maths.md`; B's stub events, then the H5 drop
- **Touches:** `cm/memory/{features,frame}.py`, `cm/memory/detectors/{weekday,trust,cusum,refill,weight}.py`
- **STEPS**
  1. `frame.py`: events → a per-patient daily grid, as pure pandas.
  2. `features.py`:
     - `q_d` trust-weighted dose probability, where τ is the reporter-trust posterior as of d−1;
     - 7/14/28-day windows;
     - the 14-day half-life decay and `n_eff`;
     - the adherence posterior `Beta`;
     - the other features (weekday misses, on-hand, reply-time median, answer rate, streaks, weight slope, payment and symptom flags, coverage).
  3. `weekday.py`: the pooled Beta (κ=4) with 4,000 seeded draws, `P(Δ>0.20)`, hypothesis/confirm thresholds, and the payday group.
  4. `trust.py`: a Beta posterior per (reporter, mode), corroboration counting and the `low_trust` flag.
  5. `cusum.py`: ln reply minutes censored at 240, MAD baseline (≥7 points), k=0.5, h=4, change day τ̂.
  6. Switch from stubs to B's H5 drop as soon as it lands.
- **Deliverable:** L1 features and the main detectors as pure functions
- **Done when:** `pytest tests/memory/test_features.py tests/memory/test_detectors.py -q` is green, including Ravi's Thursday P ∈ [0.95, 0.99] on the H5 drop, and CUSUM alarming within 2 days of day 52
- **Effort:** 3.0 h

#### 3.11 E: runtime, claim/heartbeat, governed tools, review graph (on fakes; starts H3)
- **Owner / model:** E · Sonnet
- **Inputs:** spec 02 F1 steps 4–5, F8; spec 04 F4 steps 3–6; A's and D's fakes
- **Touches:** `cm/agents/{runtime,gate,schema_guard}.py`, `cm/tools/{guard,registry,patient,detectors,review,messaging}.py`
- **STEPS**
  1. `runtime.run_job(env)`:
     - claim the `task_runs` row (a 409 when it is fresh-running, a 200 when it is a duplicate);
     - wrap the work in `async with heartbeat(task_id, every=20)`;
     - `invoke(None if attempt > 1 else input, cfg, durability="sync")`;
     - map the exception class to `failed`/200 or `retrying`/503.
  2. `tools/guard.py`, the `@governed(purpose, write)` decorator:
     - role, patient scope and task-type allowlist;
     - consent filter;
     - **`as_of` forced from the context**;
     - output tokenised;
     - 200-row cap;
     - `audit_log` with `args_hash` and `result_ids`.
  3. Read tools: `get_task_context`, `get_patient_snapshot`, `get_events`, `run_reconciler`, `compute_risk`, `list_open_reviews`.
  4. Gated tools `submit_for_review`, `send_message` and `publish_card`. On resume they upsert the same `dedup_key` and return `"queued:{outbox_id}"`; **they never send** (K3).
  5. `gate.py`, the LangGraph review graph: `persist → doctor_gate → finalize | redraft | manual_handoff | close`. Upsert **before** `interrupt()`, never inside try/except. `interrupt_id = gate:{proposal_group_id}:{redraft_count}`. Compiled with `PostgresSaver`.
  6. `schema_guard.parse(Model, text)`: one re-prompt with the Pydantic error, then a fallback.
- **Deliverable:** the agent execution and gating skeleton
- **Done when:** `pytest tests/agents/test_runtime.py tests/agents/test_gate.py tests/tools -q` is green (duplicate delivery → 200 with no re-run; a gate re-run upserts the same row; a tool's `as_of` cannot exceed the context)
- **Effort:** 3.0 h

#### 3.12 N: intake sub-agent, narrator graph and drafter (on fixtures; starts H3)
- **Owner / model:** N · Sonnet (prompts from L0 at H6)
- **Inputs:** spec 02 F2a, F2e, F2f, F7; Ravi snapshot fixtures; D's validator fake
- **Touches:** `cm/agents/subagents/{intake,narrator,drafter}.py`
- **STEPS**
  1. `intake`:
     - text wrapped in `<untrusted>`;
     - returns `ParsedInbound` with events plus `ContextNote`;
     - **never infers "taken"** (it defaults to `unclear`);
     - below 0.7 confidence, the `clarify` template;
     - `map_csv_headers` sees the headers plus 3 tokenised rows only.
  2. Narrator StateGraph: `load_bundle → load_fewshot → draft → validate → (retry_once | template_fallback) → save`. The draft uses `with_structured_output(NarrationDraft)`, with `json_schema` for OpenAI and `function_calling` for DeepSeek.
  3. Two audiences:
     - doctor: ≤5 sentences, ≤120 words, refs on every sentence;
     - Supporter: plain words, with no disease, drug or risk number.
  4. `drafter`: visit-list proposals ranked by risk × reachability (cap 6), including the week-1 `family_screen` item; Supporter briefs. All output goes to `submit_for_review` with `recipients` filled.
  5. Wrap each as a `CompiledSubAgent` with a short, decisive description.
- **Deliverable:** the LLM narration path, testable offline
- **Done when:** `pytest tests/agents/subagents -q` is green using `FakeListChatModel`: the narrator on `EvidenceBundle_ravi_d60` produces a card whose every sentence has refs; a forced number error gives the template; intake on the 40-message bank is ≥90% correct with 0 "taken" from ambiguous text
- **Effort:** 3.0 h

#### 3.13 L0: tier-2 contracts and the `openapi.json` freeze (H4)
- **Owner / model:** L0 · Opus
- **Inputs:** G's route stubs (3.6); IDD §d tier-2; M6 (`EvalReport` shape)
- **Touches:** `cm/contracts/{dashboard,admin,evalsim}.py`, `fixtures/openapi.json`, tier-2 fixtures
- **STEPS**
  1. `dashboard.py`:
     - `PatientSummary`, `PatientDetail` (+ freshness), `PatientSeries`, `FlagChip` (+ `why`), `HouseholdSummary`;
     - `ClinicSummary`, `DistrictSummary` (+ `contacts_screened_pct`), `BlockRow`, `TrendSeries`, `PaymentStuckRow`, `SuppressedInt`.
  2. `admin.py`: `LoginIn`, `Me`, `PersonAdmin*`, `RuleThresholds`, `SettingsIn/Out`, `ConsentState`, `ConsentEventIn` (the `via` regex), `ErasureRequestIn/Out`.
  3. `evalsim.py`:
     - `SimClock`, `SimInboxItem`, `TaskRunStatus` (`state`);
     - `EvalReport` in the M6 nested shape, with `facts.totals`, `safety`, `excluded` and `degraded`.
  4. Tier-2 fixtures: `DistrictSummary_demo`, `BlockRow_list_demo`, `PaymentsStuck_demo`, `EvalReport_seed42`, `SimClock_d60`, `Me_*`, `SettingsOut`, `TaskRunStatus_*`.
  5. Accept G's stubs, freeze `fixtures/openapi.json`, tag `contracts-v1.1`, and send every running agent: "rebase on `contracts-v1.1` now."
- **Deliverable:** the complete contract set
- **Done when:** `make contracts-check` is green with the tier-2 fixtures; `git tag -l contracts-v1.1` prints it; every lane reports that it has rebased
- **Effort:** 1.0 h

#### 3.14 L0: prompts and playbooks (H4:30 → H6)
- **Owner / model:** L0 · Opus
- **Inputs:** spec 02 F1 and F2 prompt outlines; IDD C26 (the investigator is P1)
- **Touches:** `cm/agents/prompts/{orchestrator,narrator_doctor,narrator_supporter,drafter,intake,query}.md`, `cm/agents/playbooks/{AGENTS,ingest_event,nightly_patient,investigate,prepare_visit_list,doctor_digest,consent_change}.md`
- **STEPS**
  1. `orchestrator.md`: plan with `write_todos`; statistics decide and the LLM explains; never compute numbers; gated tools only; the task-type allowlist.
  2. The narrator prompts (both audiences), with the exact citation grammar `[E:id] [B:id] [C:id] [R:pid@day] [G:chunk]` and the banned-word list.
  3. `drafter.md` (visit-list ranking rules, the family-screen item, no clinical advice) and `intake.md` (the untrusted wrapper, the `unclear` default).
  4. Playbooks per task type, with numbered steps. `nightly_patient` skips the investigator when it is absent (C26).
  5. Mark the prompts stable for the cassette: no timestamps, no UUIDs.
- **Deliverable:** the runtime instructions
- **Done when:** `pytest tests/agents/test_prompts_load.py` loads every file; `make banned-terms` passes over the Supporter prompt examples
- **Effort:** 1.5 h

#### 3.15 H2: district and eval page skeletons, persona switcher (starts H4, or H6 if usage ≥ 60%)
- **Owner / model:** H2 · Haiku (H1 reviews at H10)
- **Inputs:** tier-2 fixtures; spec 03 §4 and §6; UI #11
- **Touches:** `web/src/pages/{District,Eval}/`
- **STEPS**
  1. District page on `DistrictSummary_demo`: KPI tiles (including **contacts screened %**), the block table and the trend chart. Cells under 5 render as "<5".
  2. Eval page on `EvalReport_seed42`: scorecard tiles (`facts.totals`), the learning-curve chart, and the missed-pattern list.
  3. Persona switcher chips (Dr. Prasad, Lakshmi, DTO, Admin, Judge), with one-click login, behind `DEMO_MODE`.
- **Deliverable:** H2 pages on fixtures
- **Done when:** `npm run test -- District Eval` is green, and the pages render from the MSW fixtures
- **Effort:** 2.0 h

#### 3.16 Idea-round pack
- **Owner / model:** Haiku agent · Haiku; OWNER approves
- **Inputs:** `caremem_deck/project`, `docs/PS_MAPPING.md`, PREFLIGHT §C decisions 9, 10 and 13
- **Touches:** `caremem_deck/project/idea_round/`, `caremem/docs/one_pager.md`
- **STEPS**
  1. Build 5 slides:
     - the problem, led by "26.18 lakh people…" with 21% as the turn;
     - Ravi's story;
     - how it works;
     - trust (the doctor decides, no diagnosis, DPDP);
     - the architecture in one picture.
  2. One line each on the business model ("free for patients; district TB cells and private programme agencies pay per patient tracked") and the pilot ask ("Anantapur, 90 days, 200 patients, lost-to-follow-up vs last quarter").
  3. The problem-statement ID and its mapping summary on slide 1.
  4. A 60-second spoken script for Beats 1–6, and the mentor one-pager.
- **Deliverable:** an idea-round deck with no live dependency
- **Done when:** the owner says "approved", and `grep -rn "\[X/Y\]\|TODO" caremem_deck/project/idea_round` is empty
- **Effort:** 1.0 h

#### 3.17 Integration 1 (H6)
- **Owner / model:** INT · Opus
- **Inputs:** lanes A (the 3.1 core and the 3.2 `append`/`bulk_append`/`query` slice), B (3.3), D (3.4), K (3.8)
- **Touches:** `main`; `tests/integration/test_seed_integrity.py`
- **STEPS**
  1. For each lane in the order A → B → D → K: `git rebase main` in the lane, `make check`, then `git merge --no-ff lane/<x>`.
  2. Confirm that every merged lane's OpenSpec changes are archived.
  3. Cloud Build deploys `main`, and `cm-migrate` runs.
  4. Run `cm-seed` on Cloud SQL (`--seed 42 --patients 40 --days 60 --sim-day 59`, with the backfill stubbed until C lands).
  5. Write and run `test_seed_integrity.py`: 40 patients; Ravi's planted values; `truth.json` not importable outside `cm/eval`; every event has a `consent_id`.
- **Deliverable:** the first merged foundation, live on GCP
- **Done when:**
  - `make check` is green on `main`;
  - `pytest tests/integration/test_seed_integrity.py` passes against Cloud SQL;
  - `curl <cm-api>/readyz` returns 200;
  - `npx openspec list --json` shows no orphan open change for A, B, D or K.
- **Effort:** 1.0 h

### Parallelism map (Phase 3)
- **H2:30, start together:** 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8 and 3.9. No dependencies; all build on `contracts-v1` and fakes.
- **H3:** start 3.10 (on B's stubs), 3.11 (on A's and D's fakes) and 3.12 (on Ravi fixtures).
- **H4:** 3.13 waits for G's stubs (3.6 by H4). H1 regenerates its client after it. 3.15 starts after 3.13.
- **H4:30:** 3.14 runs on Opus after 3.13.
- **3.16** runs any time once 1.1 is done; it targets the idea round.
- **H5:** B's fixture drop (3.3 step 8) unblocks C's real-data runs (3.10 step 6).
- **H6:** 3.17 waits for 3.1, 3.3, 3.4, 3.8 and the 3.2 slice. 3.2 itself finishes at H7 and merges at H10.

### Phase 3 exit gate (H6)
- [ ] `contracts-v1.1` is tagged; `fixtures/openapi.json` is committed; every lane has rebased.
- [ ] `main` holds A (core slice), B, D and K; `make check` is green on `main`.
- [ ] `test_seed_integrity.py` passes on Cloud SQL; `/healthz` and `/readyz` return 200 on run.app.
- [ ] The prompts and playbooks are committed by L0.
- [ ] The idea-round deck is approved by the owner.
- [ ] Every merged lane's OpenSpec changes are archived.

### Risks and recovery
| Risk | Recovery |
|---|---|
| G's stubs are late, which blocks `openapi.json` | Freeze `openapi.json` at H4:30 from whatever stubs exist; the rest arrive by RFC. H1 continues on MSW |
| A slips past H7 | C stays on B's fixtures; INT moves an Opus review onto A's `as_of` CTE; B uses a temporary `executemany` for the seed |
| Usage above 80% | Pause K, then I, then D (after R1–R6); delay H2 to H6 |
| The Cloud Build trigger fails | I deploys with `make deploy` from the coordinator's shell; fix the trigger later |
| The deepagents API differs from the docs | E uses the `runtime.py` adapter; fall back to a plain `StateGraph` + `create_agent` (ARCH §11 #10) |

### Owner actions (Phase 3)
1. Approve the Phase 3 start and the agent cap (2 min).
2. Present the idea round when called (likely H4–H8), with the speaker; approve the deck (3.16) first.
3. Read the H4 and H6 status reports; nothing else.

---

# Phase 4: Wave 2 build, Integration 2 and the H10 cut checkpoint (H6 → H10 = 16:00–20:00)

**Phase goal.** M, J and H2 join; B starts its phase 2 work. By H10:
- C's detectors run on the real store;
- G is wired to the real store, with `decide()` in place;
- E's agents call the real tools;
- F's Telegram webhook is live, so a real tap from the owner's phone creates an event row;
- the outbox drainer and router enforce the doctor gate end to end.

Then INT merges and makes the H10 cut decision.

**Hours:** 4 h, with about 10 Sonnet and 3 Haiku agents.

### Tasks

#### 4.1 A: crypto, audit, erasure, migrations 0002–0004, `migrate.py`
- **Owner / model:** A · Sonnet
- **Inputs:** spec 04 F4 steps 7–9 and F6; IDD T5, T6, T11, I5
- **Touches:** `cm/core/{crypto,audit}.py`, `cm/store/projections.py`, `cm/store/migrations/versions/{0002_reliability,0003_security,0004_rag}.py`, `cm/jobs/migrate.py`
- **STEPS**
  1. `crypto.py`: a per-person DEK wrapped by `CM_KEK` (AES-GCM); `enc_name`, `enc_phone` and `enc_email`; HMAC blind indexes (`phone_hmac`, `nikshay_hmac`).
  2. `0002_reliability`: complete the outbox CHECK and the approved-template trigger (it rejects rows whose template is not `approved`); add the claim indexes and the `task_runs (state, heartbeat_at)` index.
  3. `0003_security`:
     - the roles `cm_app`, `cm_engine`, `cm_reader` and `cm_admin`, with grants (only `cm_engine` writes `features_daily`, `beliefs`, `conflicts` and `risk_scores`);
     - INSERT-only triggers on `events` and `audit_log`;
     - `cm.erase_person()`: crypto-shred the DEK, which also shreds `household_contacts.enc_name`, then write a `Tombstone` event.
  4. `0004_rag`: `documents` and `text_chunks` with `halfvec(1536)` (or `vector` when `RAG_VECTOR_TYPE=vector`), HNSW and GIN indexes, and the `guideline_chunks` view.
  5. `migrate.py`:
     - alembic upgrade;
     - `PostgresSaver.setup()` and `PostgresStore.setup()` in schema `lg`, with index config `fields: ["text"]` (M10);
     - assert pgvector ≥ 0.7, or the flag;
     - grants;
     - seed the playbooks into the Store.
  6. `projections.py`: rebuild `household_contacts` from `HouseholdContactEvent`s.
- **Deliverable:** a secure, reliable schema and the migrate job
- **Done when:** `pytest tests/store/test_security.py tests/store/test_outbox_check.py -q` is green, where:
  - an outbox insert with neither `decision_id` nor `template_id` raises;
  - an unapproved template raises;
  - `erase_person` makes the decrypt fail;
  - the projection rebuild equals the table;
  - `gcloud run jobs execute cm-migrate --wait` succeeds.
- **Effort:** 3.0 h

#### 4.2 B: seed job, twin-demo flag, then phase 2 (views and console backend)
- **Owner / model:** B · Sonnet
- **Inputs:** spec 04 F1 step 15; TWIN_ACCOUNT §3 #4–5; spec 03 §4 and §7; IDD T19, T20
- **Touches:** `cm/jobs/seed.py`, `cm/store/migrations/versions/0005_views.py`, `cm/api/routers/{dashboard,admin,consent,templates}.py`, `cm/api/suppress.py`
- **STEPS**
  1. Seed job steps:
     - insert persons, vault rows (seeded Faker `en_IN`, encrypted), consents and `auth_credentials` for the demo users;
     - then events via `bulk_append`;
     - then the mock Ni-kshay tables;
     - then `cm.memory.nightly.backfill(1..60)` (stubbed until C lands);
     - finally `sim_clock(seed, 59)`.
  2. `--twin-demo` (P1, behind the flag): generate seed 42 once and load it into clinics `demo_day3` (events up to day 3, `clinics.sim_day=3`) and `demo_day60` (events up to day 59), with accounts `doctor_day3`, `doctor_day60` and a Supporter per clinic.
  3. `0005_views`:
     - `v_patient_summary`;
     - `v_district_daily`, materialised, with high risk, Red over 4 h, contacts and 7-day deltas;
     - `v_review_sla`, `v_supporter_activity`, `v_payments_stuck`;
     - `v_contact_screening` (the IDD T1 shape);
     - the `cm.notify_live()` triggers on `approvals`, `review_decisions`, `task_runs`, `outbox`, `sim_clock`, `eval_runs` and `settings`, with ids only.
  4. `suppress.py`: k ≥ 5 small-cell suppression → `SuppressedInt`.
  5. Routers (as real endpoints):
     - `/dashboard/clinic/{id}/summary`;
     - district `/summary`, `/blocks`, `/trends`, `/payments-stuck`;
     - `/templates` (list, create, approve, retire, preview);
     - `/consents` (get, post);
     - `/erasure-requests` (two-person approval);
     - `/admin/persons`, `/admin/settings` (GET P0).
- **Deliverable:** a reproducible seed and the console backend
- **Done when:**
  - `python -m cm.jobs.seed --seed 42 --patients 40 --days 60 --sim-day 59` finishes in under 60 s locally;
  - `pytest tests/api/test_dashboard.py tests/api/test_consent.py tests/api/test_erasure.py -q` is green (a cell under 5 shows "<5"; the same person cannot approve their own erasure; `contacts_screened_pct` is present);
  - the twin flag run gives 2 clinics.
- **Effort:** 4.0 h (phase 2 ends at H16; this task is the first 4 h)

#### 4.3 C: risk model, lifecycle, Monte Carlo CI, `run_in_memory`
- **Owner / model:** C · Sonnet (Opus maths)
- **Inputs:** spec 02 F5 D–E; IDD M1, M4, M5; the B generator (training seeds 1000–1149)
- **Touches:** `cm/memory/{lifecycle,risk,train_risk,pipeline,snapshot}.py`, `models/risk_v1.joblib`
- **STEPS**
  1. `lifecycle.step_lifecycle`:
     - `hypothesis → confirmed → dormant → retired`;
     - stable `belief_id = uuid5(pid|kind|subject|first_seen)`;
     - `belief_evidence` links;
     - a doctor reject retires the belief and suppresses its subject; a consent withdrawal retires it with `consent_withdrawn`.
  2. `train_risk.py`:
     - generate seeds 1000–1099 (days 3–46) with the M5 labels;
     - two heads, `dropout14` and `miss7`: `LogisticRegression(l2, C=1, balanced)`;
     - isotonic calibration on seeds 1100–1149;
     - 50 bootstrap coefficient sets;
     - save to `models/risk_v1.joblib`.
  3. `risk.score_risk`:
     - 500 Monte Carlo draws (adherence Beta, trust Beta, weekday Bernoulli, a bootstrap model) → p and its 5th–95th percentile;
     - drivers `β_j(x_j − x̄_j)`, top 3;
     - if the model is missing, fall back to the prior `ci=[0.02, 0.50]`.
  4. `pipeline.run_in_memory(events_df, consents_df, as_of_days, exclude_sources=())` → the `InMemoryResult` frozen dataclass. **It takes no truth parameter**, and a signature test checks that.
  5. `snapshot.snapshot(pid, day)`: build the `MemorySnapshot` (trust lines, coverage, `unknowns`, a deterministic `headline`, `computed`, `sim_day`).
  6. Run on the real store via `as_of.query` once A merges at H10.
- **Deliverable:** the memory engine core
- **Done when:** `pytest tests/memory -q` is green, including:
  - `test_run_in_memory_has_no_truth_param`;
  - Ravi day 3 risk in `0.12±0.03` with a CI that contains `[0.04, 0.35]`;
  - Ravi day 60 risk in `0.58±0.03`;
  - no confirmed weekday belief for ≥95% of no-pattern patients over 100 seeds.
- **Effort:** 4.0 h

#### 4.4 D: cite-or-cut validator, injection scanner, identity resolver, red-team suite
- **Owner / model:** D · Sonnet (Opus reviews the validator before merge)
- **Inputs:** spec 02 F7 validator rules and F12; spec 01 F12; IDD C25
- **Touches:** `cm/validator/{cite_or_cut,numbers,banned_terms,templates}.py`, `cm/validator/injection.py`, `cm/identity/resolver.py`, `tests/redteam/`
- **STEPS**
  1. `cite_or_cut.validate(draft, bundle, audience)`:
     - every sentence has at least one ref, and every ref exists and is `as_of`-valid, else the sentence is cut;
     - the number check (ints exact, p ±0.01, % ±1, minutes ±1, kg ±0.1);
     - banned and diagnosis words (in the Supporter audience, any banned word fails the whole card);
     - at most 120 words, dropping by priority;
     - retry and fallback rules (cut_ratio > 0.4, fewer than 60% surviving).
  2. `templates.render_template(bundle, audience)`, plus a property test that every template card passes the validator.
  3. `injection.py`: a deterministic scan (instruction patterns, URLs, role strings) → `InjectionScan`. Untrusted text is always wrapped.
  4. `resolver.resolve(IdentityQuery)`:
     - normalise (honorifics, transliteration rules, `indic_transliteration` to ITRANS);
     - rapidfuzz `token_sort_ratio` + `phone_last4`;
     - bands: auto (exact key, or phone match with ≥90), review (75–90, or two candidates within 5), none (<75);
     - **never auto-merge**;
     - a linked-after-review record gets `recorded_at` = the confirm time.
  5. `tests/redteam/`: 30 validator golden cases (wrong number, foreign ID, Telugu disease word, over length) and 20 injection strings.
- **Deliverable:** the safety net for every AI sentence, and cross-source identity
- **Done when:** `pytest tests/validator tests/identity tests/redteam -q` is green; `fixtures/identity/cases.csv` (40 rows) gives the expected bands
- **Effort:** 3.5 h

#### 4.5 E: orchestrator deep agent, `interrupt_on`, persistence and resume mapping
- **Owner / model:** E · Sonnet (Opus reviews the resume code in Phase 5)
- **Inputs:** spec 02 F1 steps 1–6, F8; the deepagents signature in `cm/agents/NOTES.md`
- **Touches:** `cm/agents/{orchestrator,runtime}.py`, `cm/tools/{review,messaging}.py`
- **STEPS**
  1. `orchestrator.py`:
     - `create_deep_agent(model=get_model("ORCHESTRATOR"), system_prompt=orchestrator.md, tools=[…], subagents=[INTAKE, CURATOR, NARRATOR, DRAFTER])`;
     - middleware: TodoList, PIIGuard, ModelCallLimit(25);
     - `interrupt_on` for `submit_for_review`, `send_message` and `publish_card`;
     - a `CompositeBackend` with read-only `/memories/` and `/playbooks/`;
     - `PostgresSaver` and `PostgresStore`.
  2. An adapter layer, so a deepagents API mismatch falls back to `StateGraph` + `create_agent` without touching callers.
  3. `persist_review_items(env, interrupts)`: upsert `approvals` on `(thread_id, interrupt_id = HITL tool-call id)`, with `graph_kind='deep'`, `due_at` by tier and `proposal_group_id`; then set `task_runs` to `waiting_human`.
  4. `resume(env)`:
     - load the approval, then map by `graph_kind`;
     - deep: `Command(resume={"decisions":[{"type":"approve"|"edit"|"reject",…}]})`;
     - lg: a `ReviewDecisionIn`;
     - invoke on the same `thread_id` with `durability="sync"`;
     - redraft cap 2, then `needs_human`.
  5. `/tasks/run` and `/tasks/resume` handlers, called by G's routes through `run_job`.
- **Deliverable:** an orchestrated task that pauses at the doctor gate
- **Done when:** `pytest tests/agents/test_orchestrator.py -q` is green with fake models: a nightly task produces an interrupt and an approvals row; a re-run upserts the same row; three rejects give `needs_human`
- **Effort:** 4.0 h

#### 4.6 N: memory curator, Store projection, few-shot edits
- **Owner / model:** N · Sonnet
- **Inputs:** spec 02 F2d and F9; IDD M10
- **Touches:** `cm/agents/subagents/curator.py`, `cm/tools/dashboard.py` (read helpers only)
- **STEPS**
  1. `memory-curator`: project approved cards, beliefs and conflicts into the Store namespace `("patients", token, …)`. The curator **never** computes numbers.
  2. `apply_decision_feedback(decision_id)`, idempotent:
     - an edit → an `edit_examples` row plus a Store put of `{"text": before, "after", "kind"}` (cap 50 per doctor, FIFO);
     - a reject that cites beliefs → a `BeliefRetired` event plus a `ContextNote`.
  3. `load_fewshot`: the top 3 similar edits by embedding search on `fields:["text"]`, fed to the narrator.
  4. Wire the narrator to D's real validator once it merges (keep the fake until then).
- **Deliverable:** procedural memory from doctor edits
- **Done when:** `pytest tests/agents/test_curator.py -q` is green: an edit is stored and then retrieved as few-shot; a reject leads to the belief retiring on the next rebuild (with C's fake)
- **Effort:** 2.5 h

#### 4.7 F: outbox drainer, router checks, Supporter mode, household capture
- **Owner / model:** F · Sonnet
- **Inputs:** spec 01 F1 steps 8–13, F3, F13 steps 2–3; IDD E1 (`CheckinPrompt`), C23 (dedup)
- **Touches:** `cm/router/{outbox_drainer,quiet_hours,adapters}.py`, `cm/channels/{tg_supporter,household,supporter_web}.py`
- **STEPS**
  1. Drainer `/tasks/send` and `/tasks/drain-outbox`:
     - claim rows with SKIP LOCKED;
     - **re-run the router checks in order:** approval or template valid → consent active for (channel, purpose) → quiet hours 21:00–07:00 (Red to doctor or STS exempt) → the banned-term regex → at most 3 per recipient per day → `dedup_key` not already sent;
     - send through the adapter, then mark `sent` with `provider_message_id`.
  2. After a successful send of any check-in template, append `CheckinPrompt{outbox_id, channel, for_date, sent_at}` (key `prompt:{outbox_id}`) and enqueue `nudge-{outbox_id}` at +2 h.
  3. Error handling:
     - 429 → `next_attempt_at = now + retry_after`;
     - 403 → binding `blocked`, plus `ChannelUnreachable` (consent unchanged);
     - 3 failures → `failed`, plus a `needs_human` "channel failed" item.

     Throttle at 1 message/s per chat (advisory lock) and 20/s globally.
  4. Supporter mode (`tg_supporter.py`):
     - `/tasks/visit-lists` sends only approved `visit_list` items, in `rank` order (max 6);
     - buttons Visited–saw dose / Visited–was told / Couldn't reach / Why?;
     - `Why?` sends the approved Supporter card;
     - the result appends `SupporterVisit` plus a proxy `DoseCheckin`, then a ForceReply pill count (0–120); weight and payment when due;
     - Couldn't reach → Try tomorrow / Tell the doctor (`needs_human`);
     - the 19:00 proxy check-in appends a `CheckinPrompt{supporter_proxy}`.
  5. Household capture (`household.py`):
     - the Telegram wizard: `/family` or the visit button → relation → age band → name (ForceReply) → 4-symptom mask → Add another / Finished;
     - a consent read-back first;
     - each step appends a `HouseholdContactEvent` (key `hh:{contact_id}:{action}:{client_uuid}`) and upserts the projection through `household_repo`;
     - names are encrypted under the patient's DEK and **never** appear in events.
- **Deliverable:** the only outbound path, and the Supporter and household flows
- **Done when:** `pytest tests/router tests/channels/test_tg_supporter.py tests/channels/test_household.py -q` is green:
  - an outbox row without approval is never sent;
  - a banned term is blocked;
  - `CheckinPrompt` is appended after a send;
  - only approved visits render, in rank order;
  - Ravi's three-member wizard gives 2 `flagged`.
- **Effort:** 4.0 h

#### 4.8 M: Gmail digest, Pub/Sub inbound, reply parser, consent flows, degrade, calendar
- **Owner / model:** M · Sonnet
- **Inputs:** spec 01 F4 steps 1–5, F5 steps 2–9, F6 (`family_screen`), F11; G's `decide()` fake
- **Touches:** `cm/channels/{gmail,gmail_parse,gmail_reply,calendar,consent_flows}.py`, `cm/router/degrade.py`, `fixtures/channels/gmail/`
- **STEPS**
  1. `gmail.py`: build the client from the refresh token (with `cache_discovery=False`), wrapped in retry.
  2. Digest `/tasks/digest`:
     - Amber items plus the 10% Green sample, numbered, each with 3 evidence lines;
     - **Red under a "Console only" header, unnumbered**;
     - `T = token_urlsafe(16)`, one `approval_tokens` row per item, `sha256(T:n)`, expiring in 48 h;
     - `Reply-To: clinic+r_{T}@…`;
     - `Message-ID <digest-{doctor_id}-{date}@caremem>`;
     - the grammar printed in every digest.
  3. Inbound:
     - `/tasks/gmail-fetch` runs `history.list` from the stored cursor, falling back to `messages.list` on a 404;
     - route by the plus-tag (`+r_` reply, `+csv` P1, `+lab` P1);
     - label `CM/processed`.
  4. Reply security, all of which must pass:
     - the sender equals the doctor's binding **and** DMARC/DKIM/SPF passes;
     - `In-Reply-To` matches the digest;
     - an atomic single-use token `UPDATE … RETURNING` per item.
  5. `gmail_reply.parse`:
     - strip quoted text;
     - regexes for APPROVE/OK/YES (ALL or a range), REJECT n: reason, EDIT n: text;
     - when nothing matches, a `WORKER_MODEL` structured parse with `needs_confirm=true`, which **applies nothing**.

     Apply each command via `decide(…, via="gmail")`, then send the `gmail_echo` in the same thread.
  6. `consent_flows.record()`:
     - one transaction writes `consents`, a `ConsentEvent` and the audit row, then enqueues `consent_change`;
     - `/stop` (daily or all, binding revoked).

     `degrade.channel_profile()`: the modes full / daily_checkin / supporter_only / records_only / paused, and the fallback order.
  7. `calendar.py`: the `family_screen` P0 kind only; a deterministic event id `cm+base32hex(sha1)`; insert, then patch on 409; outcome colour on `SupporterVisit`.
- **Deliverable:** the email door into the doctor gate, plus consent
- **Done when:** `pytest tests/channels/test_gmail_*.py tests/channels/test_consent_flows.py tests/channels/test_calendar.py -q` is green, using `HttpMockSequence`:
  - `reply_approve_1-5_edit_3.eml` gives 6 `decide()` calls and 1 echo;
  - a forged or reused reply gives 0 decisions;
  - a free-form reply asks for confirmation;
  - a withdrawal drops the queued send;
  - a 403 leads to the Supporter relay.
- **Effort:** 4.0 h (live wiring in 5.4)

#### 4.9 G: `decide()`, review routes and the live patient, ingest and worker routes
- **Owner / model:** G · Sonnet (Opus reviews `decide()` at H10)
- **Inputs:** IDD K2, K3, K4, P5, P6, P7; spec 03 §1–3 backend steps
- **Touches:** `cm/review/decide.py`, `cm/api/routers/{review,patients,ingest,tasks,supporter}.py`
- **STEPS**
  1. `decide(approval_id, d, *, via, actor_id)` in **one transaction**:
     - `SELECT … FOR UPDATE` (409 `already_decided`);
     - validate (a reject on Red or Amber needs a reason; banned terms in Supporter- or patient-facing text return 422; doctor-audience number mismatches become warnings; Red cannot be decided `via="gmail"`);
     - insert `review_decisions`;
     - update `approvals.status`;
     - append `ReviewDecisionEvent` (key `decision:{approval_id}`);
     - insert `outbox` rows for each `ProposalOut.recipients` (`dedup_key = {decision_id}:{recipient_id}:{channel}:{for_date}`);
     - an `edit_examples` row on edit;
     - a `task_runs` row `resume-{approval_id}`;
     - `audit_log`.

     After commit, enqueue the resume and `drain-{channel}-{epoch_min}`.
  2. Review routes:
     - `GET /review/queue` returns `ReviewQueueOut{counts, items, next_cursor, server_time, sim_day}` in one round trip;
     - `GET /review/{id}` resolves citations against events, beliefs, conflicts and `guideline_chunks`;
     - `POST /review/{id}/decision`;
     - `POST /review/bulk-decision`, which refuses Red (`red_not_bulk`) and Amber that was not viewed (`amber_not_viewed`).
  3. Patient routes on the real store: `/patients`, `/{pid}`, `/memory`, `/card`, `/lens`, `/funnel`, `/timeline`, `/series`, `/belief-pins`, `/household` (names decrypted only for the treating doctor or the assigned Supporter), `/channel-profile`, and `GET /events|beliefs|conflicts/{id}`.
  4. Ingest routes: `/ingest/chemist-csv` (K's parser + D's resolver; files over 500 rows → 202 + `task_id`), `/ingest/supporter`, `/ingest/household-contact` (F's capture logic), `/ingest/portal`, `/ingest/lab` (structured).
  5. Worker routes, all OIDC: `/tasks/run`, `/tasks/resume`, `/tasks/send`, `/tasks/drain-outbox`, `/tasks/checkins`, `/tasks/checkin-nudge`, `/tasks/digest`, `/tasks/visit-lists`, `/tasks/gmail-*`, `/tasks/portal-sync`, `/tasks/calendar-sync`. A 503 is returned while `shutting_down`.
  6. `GET /supporter/{sid}/visit-list` (approved items only, own sid only).
- **Deliverable:** the single decision path and the live API
- **Done when:** `pytest tests/review/test_decide.py tests/api -q` is green:
  - a double decide gives 409;
  - approve → exactly one outbox row per recipient in the same transaction;
  - Red via gmail → refused;
  - bulk with Red → 422 `red_not_bulk`;
  - an edit writes an `edit_examples` row.
- **Effort:** 4.0 h

#### 4.10 H1: full review queue on fixtures (with the UI P0 items)
- **Owner / model:** H1 · Sonnet
- **Inputs:** spec 03 §1 FE steps 6–9; UI #1, #2, #3, #4, #14
- **Touches:** `web/src/pages/ReviewQueue/`, `web/src/components/{WhyFlagPopover,DiffView,UndoToast,TodayStrip}.tsx`
- **STEPS**
  1. Evidence-first detail panel: proposal, citations (`CitationChip` → `EventDrawer`), validator report.
  2. Decisions with an optimistic update; reject-reason chips; a per-sentence editor; a **word-level diff of the edit vs the AI proposal, with reason chips** (UI #3).
  3. A Green table with bulk approve; Amber viewed-tracking (it feeds `viewed_approval_ids`).
  4. The **"Why this flag" popover** on every tier badge: rule id, threshold, observed value, what would clear it (UI #2).
  5. A **10-second undo toast** after approve or reject, shown only until the outbox drains (UI #4).
  6. The **Today strip** (Red due, visits due, overdue, expiring in 2 h; UI #1) and the "All clear" empty state with a day summary (UI #14).
  7. Red countdown, escalation banner and delivery chip.
- **Deliverable:** the hero doctor screen on fixtures
- **Done when:** `npm run test -- ReviewQueue` is green; a Playwright smoke test approves an Amber item on MSW and sees the counts change
- **Effort:** 4.0 h

#### 4.11 H2: district P0 and the demo-shell pieces
- **Owner / model:** H2 · Haiku (H1 reviews at H10)
- **Inputs:** spec 03 §4; UI #10, #11, #12
- **Touches:** `web/src/pages/{District,Sim}/`
- **STEPS**
  1. District: KPI tiles (patients, high risk, Red over 4 h, **contacts screened %**, contacts referred, payments stuck), with 7-day deltas; the block table; trends; and the payments-stuck table (30/60/90).
  2. The **connection chip** (Live / Polling / Offline replay) and a red-bordered **REPLAY** banner when `CM_OFFLINE` (UI #10).
  3. The **judge guide overlay**: three things to touch, then reset (UI #12). The persona switcher is wired to `/auth/login` with the demo users (UI #11).
  4. A Sim page skeleton: sim-day badge, reset, advance and play controls (400 ms fast mode).
- **Deliverable:** the district screen and the demo shell on fixtures
- **Done when:** `npm run test -- District Sim` is green; "<5" renders for suppressed cells
- **Effort:** 4.0 h

#### 4.12 J: eval metrics and harness, sim and eval routes, replay and cassette skeleton
- **Owner / model:** J · Haiku
- **Inputs:** spec 04 F2 and F3; IDD M1, M6, P1, P2
- **Touches:** `cm/eval/{harness,metrics,facts,safety}.py`, `cm/api/routers/{sim,eval,channels}.py`, `cm/sim/{replay,cassette}.py`, `cm/jobs/eval_job.py`
- **STEPS**
  1. `metrics.py`:
     - learning curves: Brier and AUROC for model vs population average vs last week, with bootstrap CIs, from day 3 to day 60;
     - funnel (mean CI width, 90% coverage);
     - the facts scorecard per pattern, plus `totals` (planted, caught, false, false-retired, missed, precision, recall, median days to detect);
     - the missed list with a reason;
     - `SafetyCounters`.
  2. `harness.run(seed)`: generate the seed → `run_in_memory` (a fake engine until C merges) → score against `truth.json`. **Exclude scripted patients** (Ravi).
  3. `/eval?seed`:
     - a cached or under-45 s result → 200 `EvalReport`;
     - otherwise 202 + `Location: /eval/runs/{run_id}`;
     - seeds below 2000 other than 42 → 422;
     - cache on `(seed, gen_version, engine_version, model_version)`.
  4. Sim routes:
     - `POST /sim/reset` (no params = demo 42), `POST /sim/advance?to_day&mode`, `GET /sim/clock`;
     - `POST /sim/escalation-offset` and `POST /sim/sweep-now` (404 unless `DEMO_MODE=1`);
     - the sim inbox routes (404 unless `CM_OFFLINE=1`);
     - a backwards advance → 409.
  5. `cassette.py`:
     - `key = sha256(role + canonical tokenised messages + tools + response_format)`;
     - record mode via a callback;
     - replay via `CassetteChatModel` with `bind_tools`;
     - a miss raises `CassetteMiss` → the template fallback.
  6. `GET /channels` and `POST /channels/{channel}` (cut 1 if pre-accepted: leave a 404 stub).
- **Deliverable:** the re-rollable evaluation and the demo time controls
- **Done when:** `pytest tests/eval tests/replay/test_cassette.py tests/api/test_sim.py -q` is green: `/eval?seed=1500` → 422; seed 2042 with the fake engine gives an `EvalReport` that validates in the M6 shape; a cassette miss falls back to the template
- **Effort:** 4.0 h

#### 4.13 J (Sonnet sub-task): simulated phones for offline mode
- **Owner / model:** J · Sonnet (short task)
- **Inputs:** spec 04 F3 step 7; F's `handle_telegram_update`; M's `handle_gmail_reply`
- **Touches:** `cm/sim/sim_channels.py`, `tests/replay/test_sim_channels.py`
- **STEPS**
  1. `SimTelegramClient.send_message` writes a `sim_inbox` row (direction `out`) and returns a fake `message_id`.
  2. `POST /sim/inbox/{persona}/reply {callback_data|text}` builds a Telegram-shaped `Update` from a sequence and calls the **same** `handle_telegram_update()`, skipping only the secret check, behind `CM_OFFLINE`.
  3. Sim Gmail: the panel's reply text → `gmail_parse.parse_reply()` → `handle_gmail_reply()`, with the nonce and sender checks against the simulated doctor address.
  4. The channel factory swaps in the sim clients when `CM_OFFLINE=1`.
- **Deliverable:** offline phones on the same code path
- **Done when:** `pytest tests/replay/test_sim_channels.py -q` is green: a sim tap creates the same event row as a webhook tap
- **Effort:** 1.5 h

#### 4.14 Wire the live Telegram webhook and run the first real tap
- **Owner / model:** COORD · Sonnet; OWNER taps
- **Inputs:** F's webhook merged and deployed (part of 4.15, or an early cherry-pick merge at H8 if green)
- **Touches:** `infra/80_webhooks.sh`; channel binding `DEMO-RAVI`
- **STEPS**
  1. Run `scripts/set_telegram_webhook.sh`: `setWebhook` with the `secret_token`, `allowed_updates=["message","callback_query"]`, `drop_pending_updates=true`.
  2. Create the invite code `DEMO-RAVI` for P-0042 (admin route or seed).
  3. The owner sends `/start DEMO-RAVI` and completes the consent.
  4. COORD forces a check-in (`/tasks/checkins?patient=P-0042&force=1`); the owner taps Taken.
  5. Check the Cloud Run log for latency below 1 s, and that the event row exists.
- **Deliverable:** the first live connection
- **Done when:** `SELECT type, recorded_at FROM cm.events WHERE idempotency_key LIKE 'tg:%' ORDER BY recorded_at DESC LIMIT 1` returns the `DoseCheckin`, and the webhook p95 is under 1 s
- **Effort:** 0.3 h

#### 4.15 Integration 2 and the H10 cut checkpoint
- **Owner / model:** INT · Opus
- **Inputs:** A (rest of 3.2 + 4.1), C (3.10 + 4.3 detectors), G (4.9), E (3.11 + 4.5), F (3.5 + 4.7), H1 (3.7 + 4.10 slice), D (4.4, validator pending Opus review)
- **Touches:** `main`; `OPS_LOG.md`; OpenSpec `remove-*` changes
- **STEPS**
  1. **Opus reviews `decide()` (4.9) and the validator (4.4)** before they merge. These are the never-substituted reviews.
  2. Merge in dependency order A → D → C → G → E → F → H1, running `make check` before each merge. Deploy.
  3. Run `GET /patients/{ravi}/memory?day=60` against the real store; it must return non-fixture data.
  4. **Cut checkpoint:** compare each lane's ticked P0 tasks with the plan:
     - H1 or H2 more than 1.5 h behind → cut 1 and cut 2 (if they are not already pre-accepted);
     - H2 more than 2 h behind → cut 3;
     - B phase 2 or H2 admin behind → cut 4;
     - M more than 3 h behind → **do not cut 9**; reorder M (reply parsing first, calendar after) and re-check at H14.
  5. Record each cut as `remove-<feature>` (a REMOVED delta, archived), and write its "replaces on stage" line into `docs/DEMO_SCRIPT.md`. If on plan, write "H10: no cuts".
- **Deliverable:** the brain's inputs and the gate live on `main`
- **Done when:** `make check` is green on `main`; the Ravi memory endpoint serves real-store data; the cut decision is in `OPS_LOG.md`
- **Effort:** 1.5 h

### Parallelism map (Phase 4)
- **From H6, all in parallel:** 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11 and 4.12.
- **Waits:**
  - 4.3 needs A's `query` (H7) for real-store runs; it trains on the generator from H6.
  - 4.6 step 4 waits for D's validator (4.4).
  - 4.13 waits for F's `handle_telegram_update` (3.5) and M's parser (4.8, by about H8).
  - 4.14 waits for F's webhook to be deployed.
  - 4.15 waits for everything listed in its inputs at H10.
- **Re-dispatch:** each lane agent that finishes early is resumed with SendMessage on its next P0 `tasks.md` item. A new agent is spawned only if the context is too large.

### Phase 4 exit gate (H10)
- [ ] A real Telegram tap from the owner's phone creates an `events` row with `recorded_at` set, and the webhook acks in under 1 s.
- [ ] `GET /patients/{ravi}/memory?day=60` returns real-store data.
- [ ] `decide()` and the validator have passed Opus review and are merged; an outbox row without an approval or template is rejected by the database.
- [ ] `make check` is green on `main` after Integration 2.
- [ ] The H10 cut decision is recorded in `OPS_LOG.md` and as OpenSpec changes.

### Risks and recovery
| Risk | Recovery |
|---|---|
| The venue blocks Telegram | Switch on the hotspot. If it is still blocked, use the simulated phones (4.13) for the demo, and keep Telegram for the recorded video |
| C's detectors disagree with the Ravi fixture | That is expected at H10; C has until H14. N and H1 stay on the fixtures |
| The deepagents interrupt payload shape differs | The adapter (4.5 step 2) maps it. Worst case, all gating uses the LangGraph review graph (`graph_kind='lg'`) |
| An agent edits outside its lane | The hook rejects the commit; the agent files an RFC or asks the owning lane through COORD |
| The Opus review of `decide()` finds a hole | Merge is blocked until it is fixed; G pairs with Opus for 30 minutes. Nothing downstream merges ahead of it |

### Owner actions (Phase 4)
1. Do the first live tap (4.14) from your phone: about 5 minutes.
2. Attend the mentor slots booked for H6–H10, with the one-pager.
3. Read the H10 cut decision; there is no decision to make unless cut 9 comes up (it should not at H10).

---

# Phase 5: Integration 3, the brain on the real store, and the H14 cut checkpoint (H10 → H14 = 20:00–00:00)

**Phase goal.** On GCP:
- the nightly pipeline rebuilds features, beliefs, risk with Monte Carlo CIs, and conflicts R1–R6;
- the narrator writes Ravi's day-60 card on real L2, and the validator cuts uncited sentences;
- the gate pauses, and `decide()` resumes it;
- Gmail approve-by-reply works live;
- the household flag reaches the doctor queue;
- J's eval produces an `EvalReport` for three seeds.

At H14: the golden match passes and the H14 cut decision is made. **The owner can sleep from H12.**

**Hours:** 4 h, with about 9 Sonnet and 3 Haiku agents.

### Tasks

#### 5.1 C: nightly pipeline, backfill, per-clinic `as_of`, golden preparation
- **Owner / model:** C · Sonnet
- **Inputs:** spec 02 F10 and F11; IDD M1 (one engine, two drivers), C34, C40 (6 rules); twin RFC #6
- **Touches:** `cm/memory/{nightly,backfill,snapshot}.py`, `cm/jobs/nightly.py`
- **STEPS**
  1. `nightly.run(as_of, clinic_id=None)`, per patient:
     - `query` → features;
     - step the beliefs from yesterday;
     - `reconcile` (R1–R6, via D);
     - risk;
     - upsert as `cm_engine`.

     Then enqueue `nightly_patient` agent tasks for patients whose card inputs changed (`task_id nightly-{token}-d{day}`).
  2. `backfill(days=1..60)`: a full fold for the seed job (B calls it), under 60 s for 40 patients. **The same per-patient functions `run_in_memory` uses.**
  3. Per-clinic `as_of`: when `clinics.sim_day` is set, nightly and snapshot use the clinic's day (twin, P1, behind a test).
  4. Heartbeat every 20 s; respect SIGTERM between patients; a summary `NightlyReport` log line. `--as-of` overrides for `/sim/advance mode=full` (IDD C34).
  5. `/patients/{pid}/memory` and `/lens` read the stored rows. Deliver `run_in_memory` to J by H12.
- **Deliverable:** the memory engine running as a job
- **Done when:** `gcloud run jobs execute cm-nightly --args=--as-of=60 --wait` succeeds; `pytest tests/memory/test_nightly.py tests/memory/test_one_engine_two_drivers.py -q` is green (nightly rows equal the `run_in_memory` rows for the same seed and day)
- **Effort:** 4.0 h

#### 5.2 N: narrator on real L2, visit-list drafter, digest and visit playbooks
- **Owner / model:** N · Sonnet
- **Inputs:** real snapshots from 5.1; D's validator (merged); playbooks (3.14)
- **Touches:** `cm/agents/subagents/{narrator,drafter}.py`
- **STEPS**
  1. Point `build_bundle(pid, as_of)` at the real beliefs, conflicts, risk, cited events and unknowns. The drafter runs at temperature 0.
  2. Save `memory_cards` and `card_citations` (`ref_type ∈ E/B/C/R/G/D`, `ref_id` text) on `(patient_id, as_of, audience, attempt)`.
  3. `prepare_visit_list`:
     - rank by risk × reachability (max 6 per Supporter);
     - include the week-1 `family_screen` item when `treatment_start` is within days 1–7;
     - `submit_for_review(kind=visit_list)` with `recipients`.
  4. The `doctor_digest` playbook path produces the inputs M needs (pending Amber items plus the sample).
  5. Run the narrator on Ravi days 3, 28 and 60; log `cut_ratio` and `fallback_used`.
- **Deliverable:** cited cards and gated visit lists from real memory
- **Done when:** `pytest tests/agents/test_narrator_real.py -q` passes on Ravi day 60: 100% citation coverage, 0 number errors, fallback rate below 20% across days 3, 28 and 60
- **Effort:** 3.0 h

#### 5.3 E: live resume, the R6/Red review-graph path, the sweeper (Opus reviews the resume)
- **Owner / model:** E · Sonnet; Opus review
- **Inputs:** 4.5 and 4.9 merged; spec 04 F4 step 9; IDD M8, C24
- **Touches:** `cm/agents/{runtime,gate}.py`, `cm/jobs/sweeper.py`
- **STEPS**
  1. End to end on compose: nightly → narrator → `submit_for_review` interrupt → approvals row → `POST /review/{id}/decision` → `resume-{approval_id}` → the gated tool returns `queued:{outbox_id}`, with no second outbox row.
  2. The R6 and Red path: when a conflict **opens** with rule R6 (Amber) or R2/R4 (Red), `gate.py` creates one `approvals(kind=conflict)` with system text, deduplicated on `conflict_id`. Red also writes the `red_alert_doctor` template outbox row (system text). No LLM is involved.
  3. `sweeper.py`, single-flight via an advisory lock, with six duties:
     1. stale running (over 120 s) → `retrying`, then enqueue `{task_id}-a{n}`; at 6 attempts → `failed` + `needs_human`;
     2. the approval ladder: 24 h reminder, 36 h backup doctor, 48 h `expired` via `decide(via="sweeper")`; Red → STS at 4 h (`escalated_at`), honouring `escalation_offset_hours` under `DEMO_MODE`;
     3. orphan threads → re-surface the interrupts and upsert;
     4. stuck outbox → `pending`, and drain anything older than 1 minute;
     5. Gmail watch renewal when it expires within 48 h;
     6. spend cap (3 or more `spend_cap` failures in 15 minutes) → pause `agent-runs` and log an ERROR.
  4. **Opus pairs on the resume code** for idempotency: a double resume is a no-op, a node re-run upserts, and nothing is wrapped around `interrupt()`.
- **Deliverable:** the gate loop closed, and self-healing
- **Done when:** `pytest tests/agents/test_resume_e2e.py tests/jobs/test_sweeper.py -q` is green:
  - a double resume gives one outbox row;
  - killing the worker mid-run, then the sweeper, leads to the run finishing;
  - an R6 opening gives exactly one Amber approval;
  - a Red item has `escalated_at` set after the 4 h offset.

  The Opus review is recorded in `OPS_LOG.md`.
- **Effort:** 3.5 h

#### 5.4 M: Gmail live (watch, push, reply into the real `decide()`)
- **Owner / model:** M · Sonnet
- **Inputs:** 4.8; G's `decide()` merged; the `gmail-push-sub` from 0.8
- **Touches:** `cm/channels/gmail*.py`; `gmail_state`
- **STEPS**
  1. Call `users.watch` on `gmail-push` (INBOX) and store `history_id` and `expiration`. The webhook verifies OIDC and enqueues `gmail-fetch-{historyId}` → 204, with no Gmail API call.
  2. Swap the `decide()` fake for the real service; Red items have no tokens.
  3. Send a live digest to the doctor test address, then reply from the doctor's phone with `APPROVE 1-5` and `EDIT 3: Visit Wednesday evening`.
  4. Check the echo arrives in the same thread within about 20 s, the queue empties, and the resumes are enqueued.
  5. Enable the 30-minute sweep and the 06:00 renew schedules (unpause those two jobs).
- **Deliverable:** approve-by-reply, live
- **Done when:** a live reply produces exactly one `review_decisions` row per item and one outbox row per recipient (a SQL check), and a second identical reply gets "already applied"
- **Effort:** 3.0 h

#### 5.5 F: household flagging, family invite, calendar wiring, `/stop` and `/mydata`
- **Owner / model:** F · Sonnet
- **Inputs:** spec 01 F13 steps 1, 4, 7, F11 step 4; E's review graph
- **Touches:** `cm/channels/{household,tg_patient}.py`
- **STEPS**
  1. On `screened` with the flag rule true (`age_band=="<5" OR any(symptoms)`), create an Amber `approvals(kind=contact_review)` with system text only. **No recommendation, and no TPT wording** (a test asserts it).
  2. A doctor decision through `decide()` with `edited={"doctor_decision", "note"}` appends `HouseholdContactEvent{action:"doctor_decision"}`, and sets `referred=true` on `refer_test`.
  3. When the family-screen visit is approved, `decide()` queues the outbox rows `family_invite` (patient, Green template) and `cal_family_screen` (calendar), both authorised by the `decision_id`.
  4. `/stop` → `stop_menu` → M's `consent_flows`; `/mydata` → category counts; `/lang`, `/time`, `/help`.
  5. Free text: the deterministic danger keywords first, then an `ingest_event` envelope `tg-{update_id}` to intake.
- **Deliverable:** the household loop closed through the doctor
- **Done when:** `pytest tests/channels/test_household_flow.py -q` is green: Ravi's family gives 2 `contact_review` items; `refer_test` gives `referred=true`; the invite passes the banned-term check; the payload has no recommendation text
- **Effort:** 3.0 h

#### 5.6 D: validator in the loop, red-team green, identity golden
- **Owner / model:** D · Sonnet
- **Inputs:** 4.4 merged; N's real cards
- **Touches:** `cm/validator/`, `cm/identity/`, `tests/redteam/`
- **STEPS**
  1. Run the validator over 20 real Ravi and Kavya drafts, and tune only the number tokenizer (dates, "9 to 85 min", "day N"). **The rules themselves do not change.**
  2. Run `make redteam` (the injection strings through intake and the narrator; Telugu and Hindi disease words in the Supporter audience) until green.
  3. Run the identity golden on the generator's misspelt chemist rows: auto-link precision ≥ 0.98, and the borderline rows go to `approvals(kind=identity)`.
  4. Provide `reconcile_frame` to J, so the eval scores rules R1–R6 per planted conflict.
- **Deliverable:** guardrails proven on real output
- **Done when:** `make redteam` and `make banned-terms` are green; `pytest tests/identity/test_golden.py` passes
- **Effort:** 2.0 h

#### 5.7 G: SSE `/stream`, live Lens endpoints, scope hardening
- **Owner / model:** G · Sonnet
- **Inputs:** IDD P3, T20; spec 03 §0.5
- **Touches:** `cm/api/routers/stream.py`, `cm/api/realtime.py`
- **STEPS**
  1. One dedicated LISTEN connection per instance (outside the pool); a 10-minute ring buffer; `Last-Event-ID` replay; rotation at 50 s; a role and scope filter; a `LiveEvent` payload of ids only.
  2. Topics: `approvals`, `review_decisions`, `task_runs`, `outbox`, `sim_clock`, `eval_runs`, `settings`.
  3. `/patients/{pid}/lens?from=3&to=60` returns `LensComparison`; `/funnel` returns `FunnelSeries`; `/belief-pins`.
  4. Scope tests: a Supporter only sees assigned patients and approved cards; STS and DTO see aggregates only; `doctor_day3` cannot read `demo_day60` (twin test 5, if the twin seed exists).
- **Deliverable:** realtime and the Lens on live data
- **Done when:** `pytest tests/api/test_stream.py tests/api/test_scopes.py -q` is green; a decision on compose emits `approval.decided` to a connected client within 1 s
- **Effort:** 3.0 h (cut 6 replaces steps 1–2 with 5 s polling)

#### 5.8 B (phase 2 continued): remaining console backend
- **Owner / model:** B · Sonnet
- **Inputs:** 4.2
- **Touches:** B's routers, `0005_views.py`
- **STEPS**
  1. Refresh `v_district_daily` after nightly (a `REFRESH MATERIALIZED VIEW CONCURRENTLY` step called from C's job end hook).
  2. `/admin/settings` GET with `RuleThresholds` (PUT is P1); templates approve and retire with the router's 60 s cache invalidation.
  3. `POST /consents` from the console (doctor scope) → M's `consent_flows.record`.
  4. The erasure executor wiring: `cm-nightly` step C calls `cm.erase_person()` for approved requests.
- **Deliverable:** the admin, consent and erasure backend complete
- **Done when:** `pytest tests/api/test_admin.py tests/api/test_templates.py -q` is green; an approved erasure leads to a `Tombstone` event and the decrypt failing
- **Effort:** 3.0 h

#### 5.9 H1: patient list, patient overview and the Memory Lens (on fixtures, then live)
- **Owner / model:** H1 · Sonnet
- **Inputs:** spec 03 §2 and §3; UI #7, #8, #9; Ravi fixtures
- **Touches:** `web/src/pages/{Patients,Patient,Lens}/`, `web/src/components/{UncertaintyLabel,FreshnessChip}.tsx`
- **STEPS**
  1. Patient list: risk-sorted, with flags and channel chips, and an **overdue / call list** (UI #9) with one-tap "assign visit".
  2. Patient overview: headline; flags (R1–R6 `FlagChip` with why-this-flag); beliefs with citations; `EventDrawer`; **freshness chips per source** (UI #8); **plain-language uncertainty labels next to every interval** (UI #7).
  3. **Memory Lens (never cut):**
     - two panels, day 3 and day 60, from `LensComparison`;
     - a slider with **◀ ▶ step buttons** (the WCAG 2.5.7 drag alternative);
     - prefetch and `keepPreviousData`;
     - a play button;
     - the funnel chart (90% CI band narrowing), with the slider line;
     - belief pins with click-through.
  4. The 4-second drag rehearsal at 1920×1080 and 1280×720.
  5. Switch to the live API (`/lens`, `/memory?day=`) once 5.7 merges.
- **Deliverable:** the hero memory screens
- **Done when:** `npm run test -- Lens Patient` is green; a Playwright check drags day 3 → 60 and asserts the panel shows "Misses market-day Thursdays" and the risk `0.58 [0.44–0.71]`
- **Effort:** 4.0 h

#### 5.10 H2: eval and demo console, consent tab, household tab
- **Owner / model:** H2 · Haiku
- **Inputs:** spec 03 §6 and §7 frontends; tier-2 fixtures
- **Touches:** `web/src/pages/{Eval,Sim}/`, `web/src/features/patient-tabs/{Consent,Household}/`
- **STEPS**
  1. Eval:
     - a seed input (only ≥2000 is accepted, or 42; a 422 is shown inline);
     - instant cards for 2042, 2077 and 2026;
     - polling `/eval/runs/{id}` on a 202, with a progress bar;
     - scorecard tiles from `facts.totals`;
     - the learning curve with CI bands vs the population average and last week;
     - the missed-pattern list with reasons;
     - safety counters.
  2. Sim: reset, advance, a 400 ms play loop; the escalation offset and sweep-now buttons (behind `DEMO_MODE`); **phone panels** for Ravi, Lakshmi and the doctor (polling `/sim/inbox` every 1 s, tap → reply).
  3. Consent tab: the ledger per source and purpose, and a withdraw toggle → `POST /consents` (the real F11 path; it replaces cut 1 on stage).
  4. Household tab: the contacts table (names only for allowed roles), flags, the doctor decision and the screening status.
- **Deliverable:** the judge-facing eval and demo console
- **Done when:** `npm run test -- Eval Sim Consent Household` is green; the Eval page renders `EvalReport_seed42`, and entering 1500 shows the 422 message
- **Effort:** 4.0 h

#### 5.11 J: the real eval on three seeds and the cache
- **Owner / model:** J · Haiku
- **Inputs:** C's `run_in_memory` (H12); D's `reconcile_frame`
- **Touches:** `cm/eval/`, `cm/jobs/eval_job.py`, `eval_runs`
- **STEPS**
  1. Swap the fake engine for `run_in_memory`. Run `make eval SEEDS=2042,2077,2026` (200 patients each).
  2. Check the 20 s in-memory budget per seed. If it is over, profile, and move the hot loop to Sonnet (IDD note).
  3. The judge sample: a 30-card LLM judge, P1 and optional; the deterministic metrics come first.
  4. Cache the reports in `eval_runs` with the version keys. Make `cm-eval` the GCP path for 202 runs.
- **Deliverable:** real, re-rollable numbers
- **Done when:** `make eval` writes 3 `EvalReport`s whose `curves.miss7` and `facts.missed` are non-empty, and `/eval?seed=2077` returns within 30 s
- **Effort:** 3.0 h

#### 5.12 K: content finish (CSV fixtures, scenarios, report template)
- **Owner / model:** K · Haiku
- **Inputs:** B's generator CSVs; spec 01 §14 demo checklist
- **Touches:** `fixtures/channels/ch03_day44.csv`, K's mock router, templates
- **STEPS**
  1. `ch03_day44.csv`: Ravi's day-44 refill row with a misspelt name ("Ravee Kumar") that auto-links, plus one borderline row that goes to review.
  2. The Ni-kshay scenario presets for the demo (Ravi months 2–3 "paid" vs "not received").
  3. Seed the guideline chunks into `text_chunks` once 0004 is merged (`python -m cm.rag.seed`).
  4. Re-run `make banned-terms` after every template edit.
- **Deliverable:** demo-grade feed files
- **Done when:** `pytest tests/channels/test_ch03_day44.py` passes (1 auto-link, 1 review, R1 closes on day 44 with a citation)
- **Effort:** 2.0 h

#### 5.13 Integration 3 and the H14 cut checkpoint
- **Owner / model:** INT · Opus
- **Inputs:** C (5.1), N (5.2), E (5.3, Opus-reviewed), M (5.4), J (5.11), F (5.5), D (5.6), G (5.7)
- **Touches:** `main`, `tests/integration/test_ravi_golden.py`, `test_gmail_reply_live.py`
- **STEPS**
  1. Merge C → D → N → E → G → F → M → J, running `make check` before each merge. Deploy, then run the `cm-seed` job with the real backfill.
  2. Run `test_ravi_golden.py`: the real day-3 and day-60 snapshots equal the fixtures on belief keys, risk band and conflict ids, with numbers inside the CI.
  3. Run the live Gmail reply test (one decision per item, one outbox row per recipient).
  4. **Cut checkpoint:**
     - G or H1 behind on realtime → cut 6 (SSE → 5 s polling);
     - sweeper behind → cut 5 (seed a pre-escalated Red item);
     - F behind → cut 7 (ForceReply numbers) and cut 8 (3-step household wizard);
     - M cannot show a parsed reply by H16 → **ask the owner** about cut 9 (leave a message; the owner is asleep);
     - C off the golden → no cut; apply the fixture fallback until H17.
  5. Log the decisions and open the `remove-*` changes.
- **Deliverable:** the brain proven on the real store
- **Done when:** `pytest tests/integration/test_ravi_golden.py tests/integration/test_gmail_reply_live.py` passes; `make eval`, `make banned-terms` and `make redteam` are green; the H14 decisions are logged
- **Effort:** 1.5 h

### Parallelism map (Phase 5)
- **From H10, all in parallel:** 5.1, 5.2 (on fixtures until 5.1 writes rows, about H11:30), 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10 and 5.12.
- **Waits:**
  - 5.11 needs `run_in_memory` from 5.1 (H12).
  - 5.2's golden check needs 5.1.
  - 5.4 step 2 needs G's `decide()` (merged at H10).
  - 5.13 waits for all of the above at H14.
- **Owner sleeps from H12.**

### Phase 5 exit gate (H14)
- [ ] `test_ravi_golden.py` passes on the real engine.
- [ ] A live Gmail "APPROVE" reply gives exactly one `review_decisions` row and one outbox row per recipient.
- [ ] `make eval` gives `EvalReport`s for 3 seeds, with non-empty curves and missed lists.
- [ ] `make banned-terms` and `make redteam` are green.
- [ ] The Opus review of E's resume is recorded; the H14 cut decisions are logged.

### Risks and recovery
| Risk | Recovery |
|---|---|
| The LangGraph resume double-fires | `outbox.dedup_key` UNIQUE blocks the second send; E adds a test; Opus pairs for 30 minutes |
| C misses the golden | N and H1 stay on the fixture snapshots; C lands by H17; INT absorbs it. On stage, the Lens shows the fixture-backed real API |
| OpenAI 429s or a spend cap during the eval | The eval uses no LLM except the optional judge. Lower `max-concurrent-dispatches`; a spend-cap error is never retried, so wake the owner |
| The Gmail watch does not deliver | The 30-minute sweep catches up; for the demo, approve in the console and keep reply as a rehearsed bonus; ask the owner about cut 9 only at H16 |
| The eval is over its 20 s budget | Serve the precomputed seeds; move the hot loop to a Sonnet fix; the live re-roll starts at Demo cue 3 so 20–40 s is hidden |

### Owner actions (Phase 5)
1. Before sleeping (around H12), answer one standing question: "If Gmail reply is not working by H16, may we cut it (outbound digest only, approve in the console)?" Answer yes, no, or "wake me".
2. Sleep H12–H18. COORD wakes you only for a spend-cap error, a GCP billing issue, or cut 9.

---

# Phase 6: Live Ravi loop on GCP and prototype-round readiness (H14 → H18 = 00:00–04:00)

**Phase goal.** The full Ravi day-60 loop runs end to end on Cloud Run:
1. `/sim/advance` to day 60;
2. nightly;
3. card and visit list;
4. approval in the queue;
5. digest;
6. reply or console approve;
7. `decide()`;
8. outbox;
9. Lakshmi's Telegram;
10. the `Visited` tap;
11. a new event and an updated memory.

The console is wired live (queue and Lens), the schedules are on, the cassette is first recorded, and twin accounts are attempted if the usage meter allows.

**Hours:** 4 h overnight, with about 7 Sonnet and 2 Haiku agents. The owner sleeps.

### Tasks

#### 6.1 INT: write and run `test_ravi_loop.py` on GCP; route failures to lanes
- **Owner / model:** INT · Opus
- **Inputs:** `main` after Integration 3; ARCH sequence 2e
- **Touches:** `tests/integration/test_ravi_loop.py`
- **STEPS**
  1. Script the loop against the deployed URLs:
     - `POST /sim/reset?seed=42` (to day 59);
     - `POST /sim/advance?to_day=60&mode=full` → wait for the `task_id`;
     - assert Ravi's `card` and `visit_list` approvals exist;
     - trigger `/tasks/digest`, then approve (console API, and a simulated Gmail reply);
     - assert the outbox rows and that the Telegram send was recorded (`provider_message_id`);
     - a simulated Lakshmi `Visited – saw dose` callback → a `SupporterVisit` event;
     - check that `/patients/{ravi}/timeline` shows it.
  2. Add the safety assertions: 0 unapproved sends (`outbox` rows without a `decision_id` or approved template = 0); exactly one outbox row per approved recipient.
  3. Run it; turn each failure into a `fix-<name>` change, sent with SendMessage to the owning lane with the failing assertion pasted in.
  4. Re-run until it passes twice in a row after a reset.
- **Deliverable:** the integration proof for the 35% round
- **Done when:** `pytest tests/integration/test_ravi_loop.py --gcp` passes twice consecutively after `/sim/reset?seed=42`
- **Effort:** 3.0 h

#### 6.2 G + H1: wire the queue and the Lens live; delivery chip; demo banner
- **Owner / model:** H1 · Sonnet (G on call)
- **Inputs:** 5.7 SSE; 5.9 Lens; the deployed API
- **Touches:** `web/src/{api,realtime}/`, `web/src/pages/{ReviewQueue,Lens,Patient}/`
- **STEPS**
  1. Switch MSW off in production builds and point the API at `cm-api`.
  2. Make the queue live:
     - the SSE provider invalidates the queries on `approval.*`;
     - fall back to 15 s polling, or 5 s if cut 6 was taken;
     - the delivery chip reads the outbox status (queued, sent, failed).
  3. Lens live: `?day=` with prefetch of ±3 days; the play loop calls `/sim/advance` every 400 ms in fast mode.
  4. Show the `DEMO_MODE` banner when the build flag is set; deploy the web build (Cloud Run static, or the `cm-api` static mount, whichever I configured).
- **Deliverable:** the console running on real data
- **Done when:** on GCP, the console shows 1 Red / 6 Amber / 23 Green after reset; dragging the Lens from day 3 to day 60 updates both panels in under 1 s per step; approving on a second screen updates the first within 5 s
- **Effort:** 3.0 h

#### 6.3 H2: wire eval, phones and district live; agent-trace panel
- **Owner / model:** H2 · Haiku
- **Inputs:** 5.10, 5.11; `task_runs.step` and `audit_log` (`result_ids`); UI #5
- **Touches:** `web/src/pages/{Eval,Sim,District}/`
- **STEPS**
  1. Eval live: `/eval?seed`; the 202 polling path is tested with a fresh seed (e.g. 2101).
  2. Phone panels live in offline mode; with `CM_OFFLINE=0` they show "Live Telegram" and link to the QR.
  3. District live, from the `v_district_daily` refresh.
  4. **The agent-trace panel (UI #5, top demo item):** a drawer titled "How this card was made", listing the nodes and steps from `task_runs.step`, the tool calls from `audit_log` (tool, `result_ids`), the citations found and the validator cuts (`ValidatorReport`). It polls during the run.
- **Deliverable:** the judge-visible "thinks with citations" proof
- **Done when:** on GCP, opening Ravi's day-60 card shows the trace with at least 3 tool calls and the validator cut count; `/eval?seed=2101` completes through the 202 path
- **Effort:** 3.0 h

#### 6.4 E + I: the sweeper as a 5-minute job; escalation and orphan drills
- **Owner / model:** E · Sonnet; I · Haiku
- **Inputs:** 5.3
- **Touches:** `cm/jobs/sweeper.py`, `infra/70_scheduler.sh`
- **STEPS**
  1. Deploy `cm-sweeper` (timeout 240 s) and unpause its 5-minute schedule.
  2. Drill: set the escalation offset (`POST /sim/escalation-offset`, `DEMO_MODE=1`), run `/sim/sweep-now`, and check that Kavya's Red item shows `escalated_at` and that an STS alert outbox row exists.
  3. Drill: kill a worker mid-nightly (delete its revision instance or send SIGTERM locally), then check the sweeper re-enqueues and the run completes.
  4. Drill: delete an approvals row for a waiting thread, then check the sweeper rebuilds it from the checkpoint.
- **Deliverable:** self-healing proven on GCP
- **Done when:** all three drills pass and are logged in `OPS_LOG.md`
- **Effort:** 2.0 h

#### 6.5 F + M: live Supporter loop, calendar sync, nudge, consent toggle
- **Owner / model:** F · Sonnet; M · Sonnet
- **Inputs:** 5.4, 5.5; Lakshmi's phone (bound with an invite)
- **Touches:** channel code (fixes only)
- **STEPS**
  1. Bind Lakshmi's phone (`/start DEMO-LAKSHMI`); approve the day-60 visit list; check she gets "1. Ravi …" with buttons; tap `Visited – saw dose`; enter 9 tablets.
  2. Check that `/tasks/checkin-nudge` fires once at +2 h (use the fast clock) when there is no reply, and never twice.
  3. `/tasks/calendar-sync` writes "Family visit – Ravi" on approval, and it turns green after the tap.
  4. The consent toggle in the console: Telegram off → the profile becomes `supporter_only` → the card and funnel re-render → the rules still fire.
- **Deliverable:** both human sides of the loop, live
- **Done when:** the timeline shows `SupporterVisit` + `PillCount(9)`; one nudge per prompt; the calendar event exists; the toggle demo works on GCP
- **Effort:** 2.0 h (each lane 1 h)

#### 6.6 I: schedules on, min instances, alerts, cold-start check
- **Owner / model:** I · Haiku
- **Inputs:** 3.9
- **Touches:** `infra/70_scheduler.sh`, `infra/alerts/`
- **STEPS**
  1. Unpause every schedule **except** the 07:30 and 18:30 real-time check-ins (the demo uses the sim clock, which avoids surprise sends at 07:30 on demo day).
  2. Set `cm-api` and `cm-worker` to `min-instances=1`; check the pool limits (ARCH §11 #11).
  3. Add log-based alerts (P1): `banned_term_blocks > 0`, `pubsub_dead_letter_count > 0`, `spend_cap_paused`, `template_fallback_rate > 30%`.
  4. The cold-start check: after 15 minutes idle, `curl /readyz` answers in under 3 s.
- **Deliverable:** a production-shaped deploy
- **Done when:** `gcloud scheduler jobs list` shows the intended states; the `/readyz` cold timing is logged under 3 s
- **Effort:** 1.5 h

#### 6.7 J: first cassette recording and the snapshot dump
- **Owner / model:** J · Haiku
- **Inputs:** the first green 6.1 run
- **Touches:** `fixtures/cassettes/`, `fixtures/snapshots/seed42_d59.dump`, `Makefile` targets (via L0 RFC if missing)
- **STEPS**
  1. Run `make cassette-record` locally against the real models: the drafter at temperature 0, the full Ravi day-60 loop plus Kavya's Red item.
  2. Run `make cassette-check` offline and list the misses; fix unstable prompt inputs (`fix-cassette-stable-prompt`).
  3. Run `make snapshot` → `pg_dump` of the seed-42 day-59 state, matching the alembic head.
  4. Run `make offline` once to check start-to-ready time.
- **Deliverable:** the first offline-capable demo
- **Done when:** `make cassette-check` shows 3 or fewer misses (driven to 0 in 8.2), and `make offline` is ready in under 1 minute
- **Effort:** 2.0 h

#### 6.8 A + B + H2: twin accounts, Day 3 vs Day 60 (P1; only if the usage meter is below 60%)
- **Owner / model:** B · Sonnet (A and G on call); H2 · Haiku
- **Inputs:** TWIN_ACCOUNT §3–4; RFCs accepted in 2.2
- **Touches:** `cm/jobs/seed.py --twin-demo`, `cm/core/clock.py` (verified), `web/src/pages/Admin/Compare/` (H2)
- **STEPS**
  1. Run `cm-seed --twin-demo` on GCP → clinics `demo_day3` (pinned day 3) and `demo_day60` (pinned day 59, advancing to 60), with twin patients that share days 1–3.
  2. Grep for remaining clock leaks: `grep -rn "datetime.now\|sim_clock" cm/ | grep -v core/clock.py` must be empty.
  3. Bind one Telegram test chat per twin patient (F helps).
  4. H2 builds the account switcher and the **Compare page**: two API calls, the same layout side by side, behind `DEMO_MODE`.
  5. Write the 5 honesty tests in `tests/integration/test_twin.py`: identical history hash; no leakage (`as_of=3` on the day-60 twin equals the day-3 twin); isolation (a tap on day 3 changes nothing on day 60); expected outputs (7 vs 2 unknowns, the Thursday belief about 0.97); scoping.
- **Deliverable:** the twin demo (P1). The Lens slider stays the P0 fallback.
- **Done when:** `pytest tests/integration/test_twin.py --gcp` passes all 5 tests, and the Compare page renders both panels
- **Effort:** 3.0 h (skip entirely if the usage meter is at or above 60%, and log it)

#### 6.9 Prototype-round artefact capture
- **Owner / model:** Haiku agent · Haiku
- **Inputs:** a green 6.1 run; the console on GCP
- **Touches:** `caremem/docs/proto_round/`
- **STEPS**
  1. Capture a screenshot sequence (browser tools): queue, Ravi card with citations, Lens day 3 and day 60, district with contacts %, eval page.
  2. Record a 60-second screen capture of the loop (OBS, or the Windows recorder run by COORD).
  3. Write `proto_round/README.md`: what is live, what is mock, and the commit history evidence that 14 lanes merged (`git log --merges --oneline | wc -l`).
- **Deliverable:** a fallback pack for the 35% round
- **Done when:** the folder holds at least 6 screenshots, 1 video and the README
- **Effort:** 0.5 h

### Parallelism map (Phase 6)
- **6.1 starts at H14** and drives everything; the fix requests flow to the lanes.
- **In parallel from H14:** 6.2, 6.3, 6.4, 6.5, 6.6 and 6.8 (if allowed).
- **Waits:**
  - 6.7 waits for the first green 6.1 (about H16).
  - 6.9 waits for 6.1 to pass and 6.2 to be live (about H17).
  - If 6.1 is still red at H17, 6.8 stops and its agent joins the fix pool.

### Phase 6 exit gate (H18)
- [ ] `test_ravi_loop.py` passes twice in a row on GCP after reset.
- [ ] The live console shows 1 Red / 6 Amber / 23 Green, and the Lens moves from day 3 to day 60.
- [ ] Exactly one outbox row per approved recipient and 0 unapproved sends (SQL in the test).
- [ ] `/readyz` answers in under 3 s after 15 minutes idle.
- [ ] The sweeper drills pass; the first cassette is recorded.
- [ ] Twin accounts are either passing their 5 tests or logged as skipped.

### Risks and recovery
| Risk | Recovery |
|---|---|
| A Cloud Run timeout on the nightly | It runs as the `cm-nightly` job, not in `cm-api` (IDD C34) |
| Cloud SQL connection exhaustion | Apply the pool limits; switch to `DB_CONNECT_MODE=socket` |
| A joint between two lanes breaks for the first time | Each joint has a sim version; run the same loop in `CM_OFFLINE` to isolate whether it is infrastructure or logic |
| The loop is still red at H18 | Every free Sonnet slot goes to integration; no new features; 6.8 is abandoned |

### Owner actions (Phase 6)
- None. The owner sleeps. Read the `OPS_LOG.md` summary on waking (about H18).

---

# Phase 7: End-to-end hardening and the H22 feature freeze (H18 → H22 = 04:00–08:00)

**Phase goal.**
- Every never-cut item works on GCP **and** offline.
- The reliability, security and accessibility checks pass.
- The P0 UI polish is finished.
- Idle lanes take stretch items in strict order.
- The prototype round (35%, likely H18–H24) is presented on the live system.
- **Feature freeze at H22**: after that, only `fix-*` changes.

**Hours:** 4 h, with about 6 Sonnet and 2 Haiku agents.

### Tasks

#### 7.1 Run the never-cut checklist (automated plus manual)
- **Owner / model:** INT · Opus, with one verifying lane per item
- **Inputs:** the IDD §g never-cut list; `docs/DEMO_SCRIPT.md`
- **Touches:** `docs/DEMO_SCRIPT.md` (the verification table), `tests/integration/test_never_cut.py`
- **STEPS**
  1. Memory Lens: two panels, slider plus step buttons, funnel (H1).
  2. Review queue + doctor gate + outbox CHECK: an insert without approval fails in SQL (G and A).
  3. Cite-or-cut + template fallback: a forced number error gives the labelled template card (D and N).
  4. Telegram check-in with `CheckinPrompt`: a tap appends the prompt pair (F).
  5. R1–R6: each has a passing fixture and a demo-able instance in seed 42 (D).
  6. Household table + R6 + the contacts-screened % KPI moving after the wizard (F, B, H2).
  7. The `/eval?seed` re-roll, the learning curve and the missed list (J, H2).
  8. The `CM_OFFLINE` replay of the Ravi day-60 loop (J).

  Tick each one, with the verifier's name and a timestamp.
- **Deliverable:** a signed never-cut table
- **Done when:** all 8 rows are ticked in `DEMO_SCRIPT.md`, and `pytest tests/integration/test_never_cut.py` is green
- **Effort:** 2.0 h

#### 7.2 Reliability test pack
- **Owner / model:** E · Sonnet (A on call)
- **Inputs:** spec 04 F4 tests; F10
- **Touches:** `tests/reliability/`
- **STEPS**
  1. Duplicate Cloud Task delivery leads to a single run.
  2. A double resume gives one outbox row.
  3. SIGTERM mid-task leads to `retrying`, and the sweeper finishes it.
  4. A stuck `sending` outbox row goes back to `pending` after 5 minutes.
  5. A duplicate Telegram `update_id` is a no-op; a crash between send and mark gives at most 1 duplicate (documented).
  6. A spend-cap error is never retried and pauses the queue.
- **Deliverable:** reliability proven by tests
- **Done when:** `pytest tests/reliability -q` is green
- **Effort:** 2.0 h

#### 7.3 Security and privacy sweep
- **Owner / model:** D · Sonnet (G on call); Opus spot-review
- **Inputs:** spec 04 F6; CLAUDE.md non-negotiables
- **Touches:** `tests/security/`
- **STEPS**
  1. `assert_clean()` blocks a phone number or name in any LLM prompt (an integration test through the narrator).
  2. Webhook auth: a bad Telegram secret → 401; a bad Pub/Sub JWT → 401; worker routes reject requests without OIDC.
  3. Role scopes: a Supporter sees only assigned patients and approved cards; STS and DTO see aggregates with k ≥ 5 suppression; names are decrypted only for the treating doctor or the assigned Supporter.
  4. Erasure needs two people; after it runs, the decrypt fails.
  5. `make banned-terms` over the templates, the Supporter cards from the cassette, and the calendar titles.
  6. `git ls-files | xargs grep -nE "sk-|AIza|BEGIN PRIVATE"` is empty.
- **Deliverable:** a privacy posture we can defend in Q&A
- **Done when:** `pytest tests/security -q` is green, and the secret grep is empty
- **Effort:** 2.0 h

#### 7.4 UI polish to P0 (the UI research top 10, plus accessibility)
- **Owner / model:** H1 · Sonnet; H2 · Haiku
- **Inputs:** `UI_FEATURES_RESEARCH.md` §A P0 rows, §B top 10, §E
- **Touches:** `web/src/**`
- **STEPS**
  1. Confirm every UI P0 item is shipped: #1 Today strip, #2 why-this-flag, #3 edit diff, #4 undo toast, #5 agent trace, #6 synthetic banner, #7 uncertainty labels, #8 freshness chips, #9 overdue list, #10 connection chip + REPLAY, #11 persona switcher, #12 judge guide, #13 colour-blind tokens, #14 all-clear state. Ship the missing ones in rank order (5, 2, 11/12, 4, 3, 7, 10, 1/9, 6/8, 13).
  2. Greyscale test page: every tier stays distinguishable by icon and border.
  3. Accessibility: the axe check on queue, Lens, district and eval pages; keyboard path for approve, edit and reject; sticky headers do not hide focus (WCAG 2.4.11); targets at least 24 px.
  4. Empty, error and loading states on every page (spec 03 §0.8).
- **Deliverable:** a judge-proof UI
- **Done when:** the axe check shows 0 serious violations on 4 pages; a keyboard-only approve works; all 14 P0 UI items are ticked in `DEMO_SCRIPT.md`
- **Effort:** 3.0 h (split between H1 and H2)

#### 7.5 Stretch items for idle lanes only (strict order; stop at H22)
- **Owner / model:** the idle lane · Sonnet or Haiku
- **Inputs:** IDD "outside P0" list; PREFLIGHT §C #11 and #14
- **Touches:** the owning lane's directories only
- **STEPS**
  1. **Telugu templates** (K, Haiku): patient and Supporter keys only; a Telugu-speaking teammate checks every string; `make banned-terms` covers the Telugu disease words.
  2. **Pattern-investigator** (N, Sonnet): the read-only detector tools, a post-hoc citation filter, recall of at least 3 of 4 Ravi drivers.
  3. **Dashboard Q&A** (G + N, Sonnet): `POST /query`, inline in `cm-api` (25 s budget, P8), typed tools only (no SQL generation), the "tools used" footer, small-cell suppression.
  4. **Patient PWA** (H2): only if everything above is done.
- **Deliverable:** optional extras that never risk P0
- **Done when:** each stretch item ships with its own tests green, or is left unmerged at H22
- **Effort:** 0–4 h (opportunistic)

#### 7.6 Fill the slide numbers from real outputs
- **Owner / model:** Haiku agent · Haiku
- **Inputs:** `EvalReport_seed42` and the precomputed seeds; live Ravi numbers
- **Touches:** `caremem_deck/project/slides/{demo,impact,memory}.html`
- **STEPS**
  1. Replace each `[X/Y]` with the real facts scorecard numbers: caught / planted per pattern, and precision and recall.
  2. Fill the `memory.html` CI ranges from the Ravi day-3 and day-60 snapshots.
  3. Add one honest line: "Missed: N patterns, mostly from insufficient observations."
- **Deliverable:** slides with real numbers
- **Done when:** `grep -rn "\[X/Y\]\|\[QR code\]" caremem_deck/project/slides` is empty
- **Effort:** 0.5 h

#### 7.7 Prototype round (35%)
- **Owner / model:** OWNER + speaker + driver · COORD prepares
- **Inputs:** 6.1 green; the 6.9 pack; the live console
- **Touches:** none (presentation)
- **STEPS**
  1. COORD warms the system 10 minutes before: `/readyz` on api and worker, then `/sim/reset?seed=42`.
  2. Show the live loop: tap → event → queue → approve → Supporter message → Lens day 3 vs day 60 → eval with one seed.
  3. Show `make check` green and the merge history (14 lanes integrated).
  4. Keep the offline laptop open as a hot spare; the 6.9 video is the last resort.
  5. Write down the judges' questions verbatim for the Q&A bank (8.10).
- **Deliverable:** the prototype round delivered
- **Done when:** presented, with the questions logged in `OPS_LOG.md`
- **Effort:** 0.75 h (team)

#### 7.8 First full rehearsal on the real system
- **Owner / model:** OWNER, speaker, driver, doctor · COORD times it
- **Inputs:** story Beats 1–9; the live system
- **Touches:** `docs/DEMO_SCRIPT.md` (stumble log)
- **STEPS**
  1. One full 3-minute run on GCP with all four roles.
  2. COORD times each beat against the targets (0:00, 0:20, 0:30, 0:38, 0:55, 1:15, 1:45, 2:10, 2:35, 2:50).
  3. Log every stumble, and every place a live step took more than 3 s.
- **Deliverable:** a stumble list that feeds 8.6
- **Done when:** the run is logged with per-beat times
- **Effort:** 0.5 h (team)

#### 7.9 Feature freeze (H22)
- **Owner / model:** INT · Opus
- **Inputs:** 7.1–7.4 green
- **Touches:** `main`, tags
- **STEPS**
  1. Merge the last features (any stretch item that is green), running `make check` before each merge.
  2. Run `make check`, `make banned-terms` and `make redteam` on `main`.
  3. `git tag feature-freeze`; push it with the owner's standing approval.
  4. Send every agent with SendMessage: "Feature freeze: only `fix-*` changes from now on."
  5. Run `npx openspec list --json`: every open change is either archived or has a reason in `OPS_LOG.md`.
- **Deliverable:** a frozen feature set
- **Done when:** `git tag -l feature-freeze` prints the tag, and all three make targets are green on `main`
- **Effort:** 0.5 h

### Parallelism map (Phase 7)
- **From H18, in parallel:** 7.1, 7.2, 7.3, 7.4 and 7.6.
- **7.5** only in lanes with no open P0 or fix task.
- **7.7** whenever the organisers call the round.
- **7.8** after 7.7, or at about H21.
- **7.9** at H22 after 7.1–7.4.

### Phase 7 exit gate (H22)
- [ ] Every never-cut item is ticked, with a verifier, in `DEMO_SCRIPT.md`.
- [ ] `make check`, `make banned-terms`, `make redteam`, `pytest tests/reliability` and `pytest tests/security` are green on `main`.
- [ ] `/eval?seed=2077` answers in under 30 s; seed 1500 → 422.
- [ ] The 14 UI P0 items are ticked; the axe check shows 0 serious violations.
- [ ] `feature-freeze` is tagged; no open OpenSpec change lacks a reason.

### Risks and recovery
| Risk | Recovery |
|---|---|
| A never-cut item is red at H21 | Every Sonnet slot goes to it; any stretch work in progress is cancelled |
| A request for a new feature after H22 | COORD: "Logged for Q&A and the roadmap. Not built: freeze." Only an owner override reopens it, with the risk stated |
| The prototype round comes while the loop is flaky | Present on the offline laptop (the same code) and say so openly; show the GCP merge history as the integration evidence |

### Owner actions (Phase 7)
1. Wake around H18; read `OPS_LOG.md`.
2. Present the prototype round (7.7).
3. Run the first rehearsal (7.8, 30 min).
4. Name any one stretch item you want prioritised (optional).

---

# Phase 8: Demo lock: precompute, cassette, offline, business case, backup video (H22 → H30 = 08:00–16:00)

**Phase goal.** The demo works with or without the internet:
- the numbers are precomputed;
- the cassette replays with zero misses;
- the offline drill passes with Wi-Fi off;
- the demo script is locked beat by beat, with a fallback for each live moment;
- the business case and Q&A bank are written;
- the backup video exists on two devices by H30.

Only `fix-*` changes are made.

**Hours:** 8 h, with 3 Sonnet and 3 Haiku agents on fixes, plus Opus reviews.

### Tasks

#### 8.1 Precompute the demo seed and the evaluation seeds
- **Owner / model:** J · Haiku; INT checks
- **Inputs:** `feature-freeze` build
- **Touches:** `eval_runs`, `fixtures/eval/`
- **STEPS**
  1. Run `make reseed-demo` locally and the `cm-seed` job on GCP (`--seed 42 --sim-day 59`). Ravi's day-60 nightly must be **not yet run**, so it runs live on stage.
  2. Run `make eval SEEDS=42,2042,2077,2026` on GCP and locally; cache them in `eval_runs` and export them to `fixtures/eval/` for offline use.
  3. Time a fresh, non-cached seed (e.g. 2117) live, and record the seconds in `DEMO_SCRIPT.md` (the target is about 20 s).
- **Deliverable:** instant numbers on stage
- **Done when:** `/eval?seed=2042` returns 200 in under 1 s on GCP and offline
- **Effort:** 1.0 h

#### 8.2 Drive the cassette to zero misses
- **Owner / model:** J · Haiku (Sonnet for prompt-stability fixes)
- **Inputs:** 6.7
- **Touches:** `fixtures/cassettes/`, stable-prompt fixes in the owning lanes
- **STEPS**
  1. Re-record with the frozen prompts: the drafter at temperature 0, covering the full demo script (Ravi day 60, Kavya Red, Lakshmi's brief, the digest, the household items).
  2. Run `make cassette-check` offline; for each miss, find the unstable input (a timestamp, UUID or token order), fix it as `fix-cassette-stable-prompt`, and re-record.
  3. Run `tests/replay/test_offline_demo.py`: the golden card, one outbox row per recipient, 0 unapproved sends.
- **Deliverable:** network-free AI answers
- **Done when:** `make cassette-check` reports 0 misses, and `pytest tests/replay/test_offline_demo.py` passes
- **Effort:** 2.0 h

#### 8.3 Snapshot and reset paths
- **Owner / model:** J · Haiku; B on call
- **Inputs:** 8.1
- **Touches:** `fixtures/snapshots/seed42_d59.dump`, `/sim/reset`
- **STEPS**
  1. Run `make snapshot`, so the dump matches the alembic head.
  2. Time the local reset (`pg_restore --clean`; under 30 s) and the GCP reset (the `cm-seed` override; about 2 minutes, with `status=seeding|ready` shown in the UI).
  3. Add `make demo-ready`: reset → advance to 59 → warm `/readyz` → print "READY day 59".
- **Deliverable:** a one-command demo reset
- **Done when:** `make demo-ready` prints READY in under 60 s locally
- **Effort:** 1.0 h

#### 8.4 Offline drill (Wi-Fi off)
- **Owner / model:** COORD + driver · Sonnet
- **Inputs:** 8.2, 8.3
- **Touches:** none (a drill)
- **STEPS**
  1. Wi-Fi off on the spare laptop. Run `make offline` (`TASKS_MODE=local`, `CM_CASSETTE=replay`, sim channels).
  2. Run the full demo script using the phone panels and the sim Gmail reply.
  3. Check that the REPLAY banner and connection chip read "Offline replay" (being honest about it is part of the pitch).
  4. Log the start-to-ready time and any break.
- **Deliverable:** a proven hot spare
- **Done when:** the full script completes offline, with ready-time under 1 minute logged
- **Effort:** 1.0 h

#### 8.5 Bug triage (fixes only)
- **Owner / model:** 3 × Sonnet fixers; INT merges · Opus
- **Inputs:** the stumble list (7.8), drill logs, alerts
- **Touches:** the owning lanes only
- **STEPS**
  1. COORD keeps a ranked bug list in `OPS_LOG.md`: demo-blocking first, then wrong numbers, then cosmetics.
  2. Each fix is a `fix-<name>` change (`skip_specs: true` unless behaviour changes), with a test.
  3. INT merges each fix after `make check` and re-runs `test_ravi_loop.py` after every 3 merges.
- **Deliverable:** a stable build
- **Done when:** the bug list has no demo-blocking item open at H28
- **Effort:** continuous (about 6 h of agent time)

#### 8.6 Lock `docs/DEMO_SCRIPT.md` (beats, live moments, fallbacks)
- **Owner / model:** OWNER + COORD · Opus
- **Inputs:** story Beats 1–9; PREFLIGHT §C #4–8; 7.8 timings; the IDD cut replacements
- **Touches:** `docs/DEMO_SCRIPT.md`
- **STEPS**
  1. Fix the 3 live moments:
     - **7a:** the Lens slider (or the twin Compare page if 6.8 passed);
     - **7b:** the doctor approves (a Gmail reply typed "APPROVE"; console approve as the instant fallback);
     - **8:** the judge-seed result (started at Demo cue 3).
  2. For each beat, write: the exact screen, the driver's click path, the line, and the fallback if the step takes more than 5 s.
  3. The judge-seed plan: instant cards for 2042, 2077 and 2026, plus any typed seed ≥2000 (about 20 s, started early).
  4. The channel plan: live Telegram over the hotspot, with the sim phone panels in a second tab.
  5. Write in every "replaces on stage" line for the cuts that were taken.
  6. If the demo slot is not 3:00 (from 1.4), re-time the beats.
- **Deliverable:** the single source of truth for the final demo
- **Done when:** the owner approves the script and every beat has a fallback row
- **Effort:** 0.75 h

#### 8.7 Twin-account run of show (only if 6.8 passed)
- **Owner / model:** OWNER team + COORD
- **Inputs:** TWIN_ACCOUNT §5
- **Touches:** `DEMO_SCRIPT.md`, the 7a block
- **STEPS**
  1. Two windows or phones side by side, "Day 3" on the left and "Day 60" on the right; the honesty line: "Same code, same person, same seed. Only the memory differs."
  2. A judge taps "Missed" on both: on the left, an ordinary reminder; on the right, a Supporter alert plus a doctor-queue item.
  3. The doctor approves the right-hand item → Lakshmi's phone receives the brief.
  4. Close with: "At day 3 it reminds. At day 60 it understands."
  5. Rehearse it twice within 90 s; fall back to the Lens slider if two logins misbehave.
- **Deliverable:** a rehearsed twin segment
- **Done when:** 2 timed runs are each under 90 s
- **Effort:** 0.5 h

#### 8.8 Business case and market-readiness pack
- **Owner / model:** Haiku agent drafts; OWNER signs off
- **Inputs:** PITCH_PLAN business line; PREFLIGHT §C #9, #10; ARCH §12 costs; the `task_runs.cost_usd` totals
- **Touches:** `caremem_deck/project/slides/impact.html`, `caremem/docs/BUSINESS_CASE.md`
- **STEPS**
  1. **Who pays:** free for patients; district TB cells and private-sector programme agencies pay per patient tracked; CSR and Global Fund money funds the pilots.
  2. **Unit cost** from the real build telemetry: LLM cost per patient per month (from `task_runs.cost_usd` over the seed-42 run, scaled), plus Cloud Run and Cloud SQL at 200 patients. State it as an estimate with its basis.
  3. **The pilot ask:** "One 90-day pilot with Anantapur's district TB cell: 200 patients, measuring lost-to-follow-up against the previous quarter."
  4. **The honest limits slide:** mock data only; no clinical validation yet; Ni-kshay is mocked (MoU later); the investigator, Q&A and PWA are P1; and the missed patterns, with their reasons.
  5. **Regulatory posture:** DPDP itemised consent, the doctor-in-the-loop, no diagnosis claim, data minimisation (LLMs see tokens only).
- **Deliverable:** the 50%-round market half
- **Done when:** `BUSINESS_CASE.md` has all 5 sections with numbers and their sources, and `impact.html` shows the ask and the unit cost
- **Effort:** 1.5 h

#### 8.9 Write the Q&A bank
- **Owner / model:** Haiku agent drafts; COORD (Opus) sharpens
- **Inputs:** PITCH_PLAN Q&A; ARCH §11.1 "What we're missing"; the judges' questions from 7.7
- **Touches:** `caremem/docs/QA_BANK.md`
- **STEPS**
  1. Write 25 questions with 2-sentence answers, grouped: clinical safety; "isn't synthetic accuracy circular?" (the judge seed, the scripted exclusion, the misses list); privacy and DPDP; why not just reminders (the 21% and Lancet 2025 points); scale and cost; Ni-kshay integration; the business model; the team's ability to deliver.
  2. Mark the 5 most likely questions and assign each to a speaker.
  3. Add a "do not say" list: "AI diagnoses", "predicts TB", "non-compliant".
- **Deliverable:** answers ready before the drill
- **Done when:** `QA_BANK.md` has 25 entries, 5 starred, each with an owner
- **Effort:** 1.0 h

#### 8.10 Deploy hygiene and the cost check
- **Owner / model:** I · Haiku; INT checks
- **Inputs:** the current revisions
- **Touches:** Cloud Run, budgets
- **STEPS**
  1. Record the known-good revision names for `cm-api` and `cm-worker` in `OPS_LOG.md`, together with the rollback command `gcloud run services update-traffic cm-api --to-revisions=<rev>=100`.
  2. Confirm `min-instances=1` and that the 07:30 and 18:30 real check-in schedules are still paused.
  3. Check the OpenAI, DeepSeek and GCP spend against the caps; raise a cap (owner) if under 30% headroom remains.
- **Deliverable:** an instant rollback path
- **Done when:** the revision names and the rollback command are in `OPS_LOG.md`, and the spend headroom is at least 30%
- **Effort:** 0.5 h

#### 8.11 Backup video (H28 → H30)
- **Owner / model:** Haiku prepares the shot list; the team records
- **Inputs:** the locked `DEMO_SCRIPT.md`
- **Touches:** `caremem/docs/video/`
- **STEPS**
  1. Haiku writes the shot list from the script, one row per beat.
  2. The team records the full 3-minute demo (OBS or the Windows recorder), voiced by the speaker.
  3. Watch it once end to end; re-record only if a beat is broken.
  4. Save it to the laptop, a phone and a cloud drive.
- **Deliverable:** the last-resort demo
- **Done when:** the video exists on 2+ devices, is no longer than the slot, and has been watched in full once
- **Effort:** 1.0 h (team)

#### 8.12 Handout and submission prep
- **Owner / model:** Haiku · Haiku; OWNER submits
- **Inputs:** the organiser submission format (0.10)
- **Touches:** `caremem/docs/handout.pdf`; a public mirror if required
- **STEPS**
  1. A 1-page handout: Ravi's story, the loop picture, the ask, the QR code and contacts. Print it.
  2. If a public repo is required, create a secret-free mirror (the secret grep from 7.3 must be empty).
  3. Prepare the submission links (repo, video, deck) for upload at the deadline.
- **Deliverable:** a ready submission
- **Done when:** the links are listed in `OPS_LOG.md`, and the handouts are printed
- **Effort:** 0.5 h

### Parallelism map (Phase 8)
- **H22–H24:** 8.1, 8.3, 8.5, 8.8, 8.9 and 8.10 in parallel.
- **8.2** after 8.1's reseed (about H23).
- **8.4** after 8.2 and 8.3 (about H25).
- **8.6** at H22–H23 with the owner, then updated after 8.4.
- **8.7** after 8.6 (only if the twin tests passed).
- **8.11** at H28–H30, after 8.4 and the 8.5 demo-blockers are closed.
- **8.12** any time before H30.

### Phase 8 exit gate (H30)
- [ ] `make cassette-check` = 0 misses; `test_offline_demo.py` passes.
- [ ] The offline drill is done with Wi-Fi off; ready in under 1 minute.
- [ ] The eval is precomputed for seeds 42, 2042, 2077 and 2026, and answers instantly offline.
- [ ] `DEMO_SCRIPT.md` is locked and owner-approved, with a fallback per beat.
- [ ] `BUSINESS_CASE.md` and `QA_BANK.md` are complete.
- [ ] The backup video is on 2 devices and has been watched once.
- [ ] No slide placeholders remain.

### Risks and recovery
| Risk | Recovery |
|---|---|
| Prompt drift causes cassette misses | Fix the unstable input and re-record; any remaining miss falls back to the labelled template ("our safe fallback when the AI isn't sure") |
| The video recording fails | Record a phone pointed at the screen; content matters more than polish |
| Team fatigue | Two people sleep 3 hours in shifts; Haiku agents backfill tests |
| A fix breaks the loop | Roll back to the 8.10 revision; re-run `test_ravi_loop.py` |

### Owner actions (Phase 8)
1. Lock the demo-script details and the judge-seed plan (8.6, 20 minutes).
2. Sign off the business case and the pilot ask (8.8, 15 minutes).
3. Record the backup video with the team at H28–H30 (40 minutes).
4. Raise a spend cap if 8.10 asks; submit the links at the deadline.

---

# Phase 9: Rehearse and final demo (H30 → H36 = 16:00–22:00)

**Phase goal.**
- Five timed rehearsals, the last two under 3:00 with no driver stumble.
- A hard Q&A drill.
- No deploys after H32 except a revert.
- A calm final demo, worth 50%, with a hot spare and the video staged.

**Hours:** 6 h. One Haiku agent is on call for emergency fixes; Opus decides any revert.

### Tasks

#### 9.1 Tag `demo-final` and record the revisions
- **Owner / model:** INT · Opus
- **Inputs:** the H30 build
- **Touches:** git tags, `OPS_LOG.md`
- **STEPS**
  1. `git tag demo-final` on the deployed SHA, and push it.
  2. Record the `cm-api` and `cm-worker` revision names and the web build hash.
  3. Write the revert procedure as 3 commands in `OPS_LOG.md`.
- **Deliverable:** a pinned demo build
- **Done when:** `git tag -l demo-final` prints the tag, and the revisions are recorded
- **Effort:** 0.2 h

#### 9.2 Five timed rehearsals
- **Owner / model:** the team (speaker, driver, doctor, backup) · COORD times
- **Inputs:** `DEMO_SCRIPT.md`; `make demo-ready`
- **Touches:** `DEMO_SCRIPT.md` (rehearsal log)
- **STEPS**
  1. Before each run: `make demo-ready` on GCP (reset to day 59), and phones and tabs in position.
  2. Run the full 3-minute story; COORD records the time at each beat boundary against the targets (0:20, 0:30, 0:38, 0:55, 1:15, 1:45, 2:10, 2:35, 2:50, 3:00).
  3. After each run: the top 2 stumbles, and one change to wording or click path (not code).
  4. Rehearsals 1–3 on GCP; rehearsal 4 on the offline laptop (to practise the switch); rehearsal 5 on GCP as a dress run with the twin segment if it is in.
  5. The speaker memorises Beats 1, 5 and 9 word for word.
- **Deliverable:** a timed, practised demo
- **Done when:** 5 runs are logged, and runs 4 and 5 are each at or under 3:00 with no driver stumble
- **Effort:** 2.5 h (team)

#### 9.3 Q&A drill
- **Owner / model:** COORD plays a sceptical judge · Opus; the team answers
- **Inputs:** `QA_BANK.md`; ARCH §11.1
- **Touches:** `QA_BANK.md` (refined answers)
- **STEPS**
  1. 15 rapid questions, 30 s per answer, in random order, including the 5 starred ones.
  2. Score each answer: clear, honest, under 30 s. Rewrite any that fail.
  3. Drill the "do not say" list; practise "We don't know yet, and here is how the pilot measures it."
  4. A second, shorter round of 8 questions, on the weakest areas only.
- **Deliverable:** practised answers
- **Done when:** the second round has every answer passing on all three scores
- **Effort:** 1.0 h

#### 9.4 Deploy lockdown (H32)
- **Owner / model:** INT · Opus; all agents
- **Inputs:** `demo-final`
- **Touches:** none
- **STEPS**
  1. At H32, SendMessage to all agents: "No deploys. Reverts only, by Opus."
  2. Disable the Cloud Build trigger.
  3. Keep one Haiku agent on call, with the instruction "propose fixes as patches; never deploy".
- **Deliverable:** a frozen deploy
- **Done when:** `gcloud run revisions list --service cm-api` shows no revision newer than H32
- **Effort:** 0.1 h

#### 9.5 Stage the hot spare and the video
- **Owner / model:** backup person · COORD checks
- **Inputs:** 8.4, 8.11
- **Touches:** the spare laptop
- **STEPS**
  1. Spare laptop: `make offline` running, the browser on the console at day 59, the phone panels in tab 2.
  2. The video is open in a player, paused at 0:00, on the second device.
  3. Agree the switch signal: if the driver says "switching", the backup swaps HDMI within 60 s.
- **Deliverable:** a fallback ready at the stage
- **Done when:** the switch is rehearsed once and takes under 60 s
- **Effort:** 0.3 h

#### 9.6 T-15 minute checklist
- **Owner / model:** COORD + driver · Sonnet
- **Inputs:** the stage time
- **Touches:** none
- **STEPS**
  1. `curl /readyz` on `cm-api` and `cm-worker` (warm).
  2. `POST /sim/reset?seed=42` (or `make demo-ready`), then confirm day 59, Ravi's day-60 nightly not yet run, and the queue showing the expected counts.
  3. Telegram on the judges' QR phone; Lakshmi's phone unlocked; the doctor's phone on the Gmail thread.
  4. Hotspot on, with the laptop connected through it; venue Wi-Fi as the backup.
  5. The offline laptop shows READY; the video is staged.
  6. Slides on the cover; the eval tab pre-opened with the 2042/2077/2026 cards.
- **Deliverable:** everything warm
- **Done when:** all 6 items are ticked aloud by the driver
- **Effort:** 0.25 h

#### 9.7 Final demo run of show (3:00 plus Q&A)
- **Owner / model:** the team · COORD on standby
- **Inputs:** `DEMO_SCRIPT.md`
- **Touches:** none

| Time | Beat | Screen | Who does what | Fallback |
|---|---|---|---|---|
| 0:00 | 1. Meet Ravi | Cover slide | Speaker: Ravi, 32, a loader in Anantapur; Meena wakes at night | — |
| 0:20 | 2. Diagnosis day | Cover | Speaker: six months of daily tablets | — |
| 0:30 | 3. Weeks 1–3 | Cover | Speaker: he feels better | — |
| 0:38 | 4. The quiet slide | Cover (red dots) | Speaker points at the missed Thursdays, the refill gap, the payment, the unread lab | — |
| 0:55 | 5. Six people, six pieces | Problem slide | Speaker: 26.18 lakh; "today's alerts are mostly wrong" (21%) | — |
| 1:15 | 6. What if someone remembered? | How-it-works slide | Speaker: statistics find, the AI explains with citations, the doctor approves | — |
| 1:45 | **7a. Day 3 vs Day 60 (LIVE)** | Console, Lens (or the twin Compare page) | Driver drags the slider from day 3 to day 60 (or a judge taps "Missed" on both twin phones); speaker reads the Thursday belief, trust 0.41, risk 0.58 [0.44–0.71] | Step buttons ◀ ▶ → the Lens fixture → the video |
| 2:10 | **7b. The doctor decides (LIVE)** | Queue → Gmail → Lakshmi's phone | The doctor replies "APPROVE" (or approves in the console); Lakshmi's phone receives "Ravi first"; **Demo cue 3: the backup starts the judge-seed re-roll** | Console approve → sim phone panel |
| 2:35 | **8. The ending (LIVE)** | Eval page | Show the judge's seed: learning curve, caught / planted, the missed list; "Meena sleeps through the night" (a 2-second pause) | A precomputed 2042 card |
| 2:50 | 9. The ask | Impact slide | Speaker: the Anantapur 90-day pilot, 200 patients, lost-to-follow-up vs the previous quarter; "He needs someone who remembers." | — |
| 3:00 | Q&A | Impact slide stays up | The assigned speakers answer from `QA_BANK.md`; the driver keeps the console ready to show evidence | — |

- **Deliverable:** the final demo
- **Done when:** delivered within the slot
- **Effort:** 0.25 h on stage

#### 9.8 Post-demo: submission, retro, shutdown
- **Owner / model:** OWNER submits; COORD writes the retro · Sonnet
- **Inputs:** the 8.12 links
- **Touches:** `OPS_LOG.md`
- **STEPS**
  1. Upload the submission (repo or mirror link, video, deck) before the deadline.
  2. COORD writes a 10-line retro in `OPS_LOG.md`.
  3. Stop all agents; pause the schedules (so they don't keep charging); keep the services up until judging ends.
- **Deliverable:** the hackathon closed cleanly
- **Done when:** the submission is confirmed, the retro is written, and the schedules are paused
- **Effort:** 0.3 h

### Parallelism map (Phase 9)
- 9.1 at H30.
- 9.2 and 9.3 alternate between H30 and H34 (rehearse, drill, rehearse).
- 9.4 at H32.
- 9.5 before rehearsal 4.
- 9.6 at stage time minus 15 minutes.
- 9.7 on stage.
- 9.8 afterwards.

### Phase 9 exit gate
- [ ] 5 rehearsals are logged; the last 2 are each at or under 3:00 with no driver stumble.
- [ ] `demo-final` is tagged; no revision is newer than H32.
- [ ] The hot spare and the video are staged; the switch is rehearsed in under 60 s.
- [ ] The second Q&A drill round passes on every answer.

### Risks and recovery
| Risk | Recovery |
|---|---|
| Telegram fails on the venue network | Use the sim phone panels on the projector (the same code path) |
| A judge picks a seed we did not precompute | Start the live `/eval?seed` at Demo cue 3 (about 20 s); show the 2042 card if it is not back |
| Cloud Run is down | The offline laptop; if that also fails, the video plus live narration |
| The doctor misses the approve cue | The driver approves in the console; the speaker keeps talking |

### Owner actions (Phase 9)
1. Lead the rehearsals and the Q&A drill.
2. Approve the revert-only rule at H32.
3. Present; submit the links; stop the agents afterwards.

---

# Feature coverage check (every spec feature lands in a task)

| Feature | Tasks that build or prove it |
|---|---|
| Telegram check-in (with `CheckinPrompt`) | 0.4, 3.5, 4.7 (steps 1–3), 4.14, 7.1 |
| Supporter flows (visit list, brief, pill count, proxy check-in) | 4.7 (step 4), 5.2 (step 3), 6.5 |
| Doctor queue and database-enforced gate | 2.4 (outbox CHECK), 3.11 (review graph), 4.1 (trigger), 4.5, 4.9 (`decide()`), 4.10, 5.3, 6.2 |
| Gmail digest and approve-by-reply | 0.5, 4.8, 5.4 |
| Calendar (`family_screen` P0; refill, test and visit P1) | 4.8 (step 7), 5.5 (step 3), 6.5 |
| Chemist CSV | 3.8 (step 4), 4.9 (step 4), 5.12 |
| Consent ledger and degradation | 3.5 (step 4), 3.2 (step 4), 4.8 (step 6), 5.8, 5.10 (step 3), 6.5 (step 4) |
| Identity resolution | 4.4 (step 4), 5.6 (step 3) |
| Household screening and R6 | 3.3 (step 5), 3.4 (step 3), 4.2 (`v_contact_screening`), 4.7 (step 5), 4.11 (KPI), 5.3 (step 2), 5.5, 7.1 |
| Memory engine and beliefs (L1, L2, lifecycle, risk, Monte Carlo CI) | 3.10, 4.3, 5.1 |
| Rules R1–R6 | 3.4, 5.6 (step 4) |
| Narrator and cite-or-cut | 3.12, 4.4 (steps 1–2), 5.2, 7.1 |
| Orchestrator and sub-agents | 3.11, 3.12, 3.14, 4.5, 4.6, 7.5 (investigator, P1) |
| Memory Lens | 5.7 (step 3), 5.9 (step 3), 6.2 |
| Dashboards (clinic, district, KPIs) | 4.2, 4.11, 5.8, 5.9, 6.3 |
| Dashboard Q&A (P1) | 7.5 (step 3) |
| Demo and eval console (judge re-roll) | 4.11 (step 4), 4.12, 5.10, 5.11, 6.3, 8.1 |
| Offline replay (`CM_OFFLINE`, cassette, sim phones) | 4.12 (step 5), 4.13, 6.7, 8.2, 8.3, 8.4 |
| Reliability (`task_runs`, outbox, sweeper, SIGTERM) | 3.1, 3.2, 4.1, 4.7 (steps 1–3), 5.3 (step 3), 6.4, 7.2 |
| Deployment (GCP) | 0.2, 0.6, 0.8, 2.6, 3.9, 6.6, 8.10, 9.1, 9.4 |
| Twin accounts (P1) | 0.13, 2.2, 3.1 (step 2), 4.2 (step 2), 5.1 (step 3), 5.7 (step 4), 6.8, 8.7 |
| UI polish (UI_FEATURES_RESEARCH P0 #1–14) | 3.7, 4.10, 4.11, 5.9, 6.3, 7.4 |
| Ni-kshay mock and R3 | 3.3, 3.8 (step 5), 5.12 (step 2) |
| Auth, security, privacy, guardrails | 3.6, 4.1, 4.4 (step 3), 5.7 (step 4), 7.3 |
| Business case and pitch | 0.12, 1.1, 3.16, 7.6, 8.8, 8.9, 9.3 |

---

# Task index (all 109 tasks)

| ID | Task | Lane | Model | h | Phase |
|---|---|---|---|---|---|
| 0.1 | Coordinator to Sonnet; open ops log | OWNER+COORD | Sonnet | 0.1 | 0 |
| 0.2 | GCP project, budgets, APIs; start Cloud SQL | OWNER+COORD | Sonnet | 0.25 | 0 |
| 0.3 | LLM keys, spend caps, model IDs | OWNER+COORD | Sonnet | 0.3 | 0 |
| 0.4 | Telegram bots and judge QR | OWNER | Sonnet | 0.25 | 0 |
| 0.5 | Gmail inbox, OAuth, refresh token, calendar | OWNER+COORD | Sonnet | 0.3 | 0 |
| 0.6 | IAM, secrets, queues, Pub/Sub, bucket | COORD+OWNER | Sonnet | 0.35 | 0 |
| 0.7 | Local env, pins, deepagents signature | COORD | Sonnet | 0.4 | 0 |
| 0.8 | Cloud SQL ready, pgvector check, smoke deploy | COORD | Sonnet | 0.4 | 0 |
| 0.9 | `scaffold-v0` commit, push, Cloud Build link | COORD+OWNER | Sonnet | 0.2 | 0 |
| 0.10 | Organiser check, mentor booking | OWNER | — | 0.2 | 0 |
| 0.11 | Roles, sleep plan, commit permission, kit | OWNER | — | 0.25 | 0 |
| 0.12 | Problem-statement pre-mapping, pitch hygiene | COORD | Sonnet | 0.4 | 0 |
| 0.13 | Pre-freeze RFC pack (twin, UI) | COORD | Sonnet | 0.3 | 0 |
| 1.1 | Lock statement, `PS_MAPPING.md` | COORD | Opus | 0.35 | 1 |
| 1.2 | Spawn L0 | COORD | Opus | 0.05 | 1 |
| 1.3 | Spawn I for leftovers | COORD→I | Haiku | 0.05 | 1 |
| 1.4 | Confirm round times, re-base clock | OWNER | — | 0.1 | 1 |
| 1.5 | Go/no-go, pre-accepted cuts, agent cap | OWNER+COORD | Opus | 0.1 | 1 |
| 2.1 | Lanes scaffold, ownership hook, `CLAUDE.md` | L0 | Opus | 0.3 | 2 |
| 2.2 | Decide pre-freeze RFCs | L0 | Opus | 0.15 | 2 |
| 2.3 | Tier-1 contracts | L0 | Opus | 1.0 | 2 |
| 2.4 | `0001_core` migration | L0 | Opus | 0.5 | 2 |
| 2.5 | `maths.md` and `generator.md` | L0 | Opus | 0.25 | 2 |
| 2.6 | Infra skeleton (Docker, deploy, Cloud Build) | I | Haiku | 2.0 | 2 |
| 2.7 | Tier-1 golden fixtures | L0 | Opus | 0.5 | 2 |
| 2.8 | Tag `contracts-v1`, worktrees, hook test | COORD | Opus | 0.15 | 2 |
| 3.1 | Core runtime modules | A | Sonnet | 2.5 | 3 |
| 3.2 | Event store and repositories | A | Sonnet | 3.0 | 3 |
| 3.3 | World generator and H5 fixture drop | B | Sonnet | 3.0 | 3 |
| 3.4 | Rules R1–R6, `reconcile_frame`, fast path | D | Sonnet | 2.5 | 3 |
| 3.5 | Telegram client, webhook, binding, check-in | F | Sonnet | 3.5 | 3 |
| 3.6 | Auth, route stubs, `openapi.json` | G | Sonnet | 3.5 | 3 |
| 3.7 | Console shell, tokens, login, queue skeleton | H1 | Sonnet | 3.5 | 3 |
| 3.8 | Templates, text bank, CSV parser, Ni-kshay, RAG seed | K | Haiku | 3.5 | 3 |
| 3.9 | Skeleton deploy, trigger, paused schedules | I | Haiku | 2.0 | 3 |
| 3.10 | Features L1 and first detectors | C | Sonnet | 3.0 | 3 |
| 3.11 | Runtime, governed tools, review graph | E | Sonnet | 3.0 | 3 |
| 3.12 | Intake, narrator graph, drafter | N | Sonnet | 3.0 | 3 |
| 3.13 | Tier-2 contracts, `contracts-v1.1` | L0 | Opus | 1.0 | 3 |
| 3.14 | Prompts and playbooks | L0 | Opus | 1.5 | 3 |
| 3.15 | District and eval skeletons, persona switcher | H2 | Haiku | 2.0 | 3 |
| 3.16 | Idea-round pack | Haiku agent | Haiku | 1.0 | 3 |
| 3.17 | Integration 1 | INT | Opus | 1.0 | 3 |
| 4.1 | Crypto, audit, erasure, migrations 0002–0004 | A | Sonnet | 3.0 | 4 |
| 4.2 | Seed job, twin flag, views, console backend | B | Sonnet | 4.0 | 4 |
| 4.3 | Risk model, lifecycle, MC CI, `run_in_memory` | C | Sonnet | 4.0 | 4 |
| 4.4 | Validator, injection, identity, red team | D | Sonnet | 3.5 | 4 |
| 4.5 | Orchestrator, `interrupt_on`, resume mapping | E | Sonnet | 4.0 | 4 |
| 4.6 | Memory curator, Store, few-shot edits | N | Sonnet | 2.5 | 4 |
| 4.7 | Drainer, router checks, Supporter, household capture | F | Sonnet | 4.0 | 4 |
| 4.8 | Gmail digest and inbound, consent, degrade, calendar | M | Sonnet | 4.0 | 4 |
| 4.9 | `decide()`, review, patient, ingest and worker routes | G | Sonnet | 4.0 | 4 |
| 4.10 | Full review queue with UI P0 items | H1 | Sonnet | 4.0 | 4 |
| 4.11 | District P0, connection chip, judge guide, sim shell | H2 | Haiku | 4.0 | 4 |
| 4.12 | Eval harness, sim and eval routes, cassette | J | Haiku | 4.0 | 4 |
| 4.13 | Simulated phones (offline) | J | Sonnet | 1.5 | 4 |
| 4.14 | Live Telegram webhook, first real tap | COORD+OWNER | Sonnet | 0.3 | 4 |
| 4.15 | Integration 2, H10 cut checkpoint | INT | Opus | 1.5 | 4 |
| 5.1 | Nightly pipeline, backfill, per-clinic `as_of` | C | Sonnet | 4.0 | 5 |
| 5.2 | Narrator on real L2, visit-list drafter | N | Sonnet | 3.0 | 5 |
| 5.3 | Live resume, R6/Red graph, sweeper | E | Sonnet | 3.5 | 5 |
| 5.4 | Gmail live approve-by-reply | M | Sonnet | 3.0 | 5 |
| 5.5 | Household flagging, invite, calendar, `/stop` | F | Sonnet | 3.0 | 5 |
| 5.6 | Validator in loop, red team, identity golden | D | Sonnet | 2.0 | 5 |
| 5.7 | SSE `/stream`, Lens endpoints, scopes | G | Sonnet | 3.0 | 5 |
| 5.8 | Remaining console backend (admin, consent, erasure) | B | Sonnet | 3.0 | 5 |
| 5.9 | Patients, overview, Memory Lens | H1 | Sonnet | 4.0 | 5 |
| 5.10 | Eval and demo console, consent and household tabs | H2 | Haiku | 4.0 | 5 |
| 5.11 | Real eval on three seeds, cache | J | Haiku | 3.0 | 5 |
| 5.12 | Content finish (CSV fixture, scenarios) | K | Haiku | 2.0 | 5 |
| 5.13 | Integration 3, H14 cut checkpoint | INT | Opus | 1.5 | 5 |
| 6.1 | `test_ravi_loop.py` on GCP, triage | INT | Opus | 3.0 | 6 |
| 6.2 | Queue and Lens live, delivery chip | H1 (+G) | Sonnet | 3.0 | 6 |
| 6.3 | Eval, phones, district live; agent trace | H2 | Haiku | 3.0 | 6 |
| 6.4 | Sweeper job and drills | E+I | Sonnet+Haiku | 2.0 | 6 |
| 6.5 | Live Supporter loop, calendar, nudge, toggle | F+M | Sonnet | 2.0 | 6 |
| 6.6 | Schedules, min instances, alerts, cold start | I | Haiku | 1.5 | 6 |
| 6.7 | First cassette, snapshot dump | J | Haiku | 2.0 | 6 |
| 6.8 | Twin accounts (P1) | B+H2 (A, G) | Sonnet+Haiku | 3.0 | 6 |
| 6.9 | Prototype-round artefacts | Haiku agent | Haiku | 0.5 | 6 |
| 7.1 | Never-cut checklist | INT | Opus | 2.0 | 7 |
| 7.2 | Reliability test pack | E (+A) | Sonnet | 2.0 | 7 |
| 7.3 | Security and privacy sweep | D (+G) | Sonnet | 2.0 | 7 |
| 7.4 | UI polish to P0, accessibility | H1+H2 | Sonnet+Haiku | 3.0 | 7 |
| 7.5 | Stretch items (idle lanes only) | K / N / G / H2 | mixed | 0–4 | 7 |
| 7.6 | Slide numbers from real outputs | Haiku agent | Haiku | 0.5 | 7 |
| 7.7 | Prototype round | OWNER team | — | 0.75 | 7 |
| 7.8 | First full rehearsal | OWNER team | — | 0.5 | 7 |
| 7.9 | Feature freeze | INT | Opus | 0.5 | 7 |
| 8.1 | Precompute demo and eval seeds | J | Haiku | 1.0 | 8 |
| 8.2 | Cassette to zero misses | J | Haiku | 2.0 | 8 |
| 8.3 | Snapshot and reset, `make demo-ready` | J (+B) | Haiku | 1.0 | 8 |
| 8.4 | Offline drill | COORD+driver | Sonnet | 1.0 | 8 |
| 8.5 | Bug triage, fixes only | 3 fixers + INT | Sonnet+Opus | 6.0 | 8 |
| 8.6 | Lock `DEMO_SCRIPT.md` | OWNER+COORD | Opus | 0.75 | 8 |
| 8.7 | Twin run of show (if 6.8 passed) | OWNER team | — | 0.5 | 8 |
| 8.8 | Business case pack | Haiku agent + OWNER | Haiku | 1.5 | 8 |
| 8.9 | Q&A bank | Haiku agent + COORD | Haiku+Opus | 1.0 | 8 |
| 8.10 | Deploy hygiene, cost check | I | Haiku | 0.5 | 8 |
| 8.11 | Backup video | team + Haiku | Haiku | 1.0 | 8 |
| 8.12 | Handout, submission prep | Haiku agent + OWNER | Haiku | 0.5 | 8 |
| 9.1 | Tag `demo-final`, record revisions | INT | Opus | 0.2 | 9 |
| 9.2 | Five timed rehearsals | team + COORD | — | 2.5 | 9 |
| 9.3 | Q&A drill | COORD + team | Opus | 1.0 | 9 |
| 9.4 | Deploy lockdown (H32) | INT | Opus | 0.1 | 9 |
| 9.5 | Stage hot spare and video | backup | — | 0.3 | 9 |
| 9.6 | T-15 checklist | COORD+driver | Sonnet | 0.25 | 9 |
| 9.7 | Final demo run of show | team | — | 0.25 | 9 |
| 9.8 | Submission, retro, shutdown | OWNER+COORD | Sonnet | 0.3 | 9 |

**Totals.** 109 tasks, about 192 hours (agent plus people), plus up to 4 hours of stretch work.
- **Build phases 3–6:** about 150 agent-hours. That fits 14 lanes × 19.5 h (273 h) at about 55% before overrun, and about 72% at a 1.3× overrun.
- **Critical path (IDD §e):** 2.3 → 3.2 → 4.3 → 5.1 → 5.2 + 5.3 → 6.2 → 6.1, with about 1.5 h of slack before H22.

---

# What can be cut, in order

Cut from the top. Every cut is final, logged as an OpenSpec `remove-*` change, and has its stage replacement written into `DEMO_SCRIPT.md`. The INT lane makes the cut at the H10 and H14 checkpoints. Cut 9 needs the owner's yes.

| Order | Cut | Task(s) affected | Saves | What replaces it on stage |
|---|---|---|---|---|
| A | Stretch items: Telugu, investigator, Q&A, PWA | 7.5 | 0–4 h | Roadmap slide and Q&A answer |
| B | Twin accounts (P1) | 6.8, 8.7 | 3.5 h | The Memory Lens slider (P0) |
| C | UI P1 items: audit tab, hover preview, escalation stepper, dark mode, keyboard sheet, timeline replay | 7.4 (P1 rows) | about 6 h | Not shown |
| 1 | Channel kill switches + what-if (`/channels`, `exclude_sources`, M7) | 4.12 step 6, 5.9 | 3 h | The consent-withdrawal toggle (the real F11 path) + `trust.html` |
| 2 | Timeline lanes tab | H1 timeline | 2 h | Overview citations + `EventDrawer` |
| 3 | Charts tab | H2 patient tabs | 2 h | The refill-gap conflict's evidence in the drawer |
| 4 | Admin users and roles page | 4.2 step 5 (persons), H2 admin | 2 h | Seeded users; keep templates approve + consent |
| 5 | Escalation fast-forward + sweep-now | 4.12 step 4, 6.4 step 2 | 1 h | A pre-escalated Red item in the seed |
| 6 | SSE `/stream` | 5.7 steps 1–2, 6.2 step 2 | 3 h | 5 s polling; Beat 7b flips within 5 s |
| 7 | Supporter ForceReply numbers (pill count, weight) | 4.7 step 4 | 1.5 h | Visited buttons; pill count through `/ingest/supporter` |
| 8 | Household wizard → a 3-step minimal flow | 4.7 step 5 | 0.75 h | Same events, table, R6 and KPI |
| D | Agent-trace panel (UI #5) | 6.3 step 4 | 2 h | The validator report in the queue detail |
| 9 | Gmail approve-by-**reply** (owner's yes required) | 4.8 steps 3–5, 5.4 | 5 h | Outbound digest only; the doctor approves in the console |

**Never cut:** the Memory Lens; the review queue + doctor gate + outbox CHECK; cite-or-cut + template fallback; Telegram check-in with `CheckinPrompt`; R1–R6; the household table + R6 + contacts-screened % KPI; the `/eval?seed` re-roll + learning curve + missed list; the `CM_OFFLINE` replay of the Ravi day-60 loop.

---

# Usage-limit playbook (8 lines)

1. **Stagger Opus.** None before H0; then contracts at H0–H5, integrations and RFCs at H5–H15, the loop at H15–H20, the freeze at H20–H25. Log every reset time in `OPS_LOG.md`.
2. **Cap agents by the usage meter.** 11 at peak; 8 above 60%; 5 above 80% (critical path only: A, C, E, N, G, H1); 2 above 95%.
3. **Pause in this order:** K → I → D → H2 → J → B phase 2 → M → F → H1 → G → N → E → C → A.
4. **When Opus is capped,** Sonnet merges only lanes that are green and conflict-free, and accepts only additive RFCs. The validator and gate reviews always wait for Opus.
5. **Checkpoint constantly.** Every agent commits after each task (at least every 45 minutes) and keeps a `RESUME POINT` block in its `NOTES.md`.
6. **After a 429,** resume the same agent ID with SendMessage: "Resume from your RESUME POINT; run `git log -3` and the last failing test first." Never run two agents on one lane.
7. **While waiting for a reset,** run the no-LLM work from the shell: `make check` per lane, `reseed-demo`, `offline`, `cassette-check`, `deploy`; and people work (rehearse, mentors, hotspot test).
8. **Model fallback:** thinking work goes Opus → Sonnet → wait; building goes Sonnet → Opus (only with headroom) → Haiku (tiny, test-defined tasks); test-defined work goes Haiku → Sonnet. A cap lasting more than 45 minutes on the critical path means re-plan and tell the owner which beat is at risk.

---

# Added tasks: AI budget governor

From section 5 of `AI_LIMITS_AND_CAPS.md`. Code exists in `caremem/cm/core/{budget,retry,llm,tokenize,lifecycle}.py`; these tasks wire and prove it. Existing tasks are unchanged.

| Phase / lane | Task | Size | Model |
|---|---|---|---|
| 3, lanes A and E | Wire the governor and circuit breaker: `get_model` everywhere, `RunBreaker` in `runtime.py` (trip becomes a "needs a human" review item), DB-backed `UsageStore` writing `task_runs` tokens_in, tokens_out, cost_usd, `error_class` | about 3 h | Sonnet |
| 4, lane I | Owner alerts at 70%, 90% and on 402 (`pending_alerts` to outbox system kinds) and env config (`CM_BUDGET_*`, `CM_PRICE_TABLE_JSON`, `*_MODEL`) | about 1 h | Haiku |
| 7 | RED-mode drill: cut credits on purpose (or `mark_billing_error`), confirm template-only mode and cassette replay work | about 1 h | Sonnet |
| 8 | Usage-and-caps panel (`usage_numbers`) on screen in the last rehearsal | about 1 h | Sonnet |
