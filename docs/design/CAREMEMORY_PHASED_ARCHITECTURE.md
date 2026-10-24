# CareMemory: phased architecture and agent plan (mermaid)

How to read this: the **system** is one architecture. It gets **built in 10 phases** (0 to 9) by **14 lane agents plus Opus**, each lane owning its own folders. Final names come from `INTEGRATION_DECISIONS.md`; the clock assumes H0 = 10:00 Saturday 24 Oct (confirm the real start).

Model key: **Opus** thinks and integrates. **Sonnet** and **Haiku** build. Runtime models inside the product are OpenAI or DeepSeek only.

---

## 1. The whole system, coloured by the phase in which each piece first works

Colour = the phase in which that piece first works end to end. Lanes keep refining it afterwards.

```mermaid
flowchart TB
  classDef p2 fill:#E6F4F1,stroke:#0F766E,color:#1F2933
  classDef p3 fill:#E3EEF9,stroke:#2563EB,color:#1F2933
  classDef p4 fill:#EDE7F6,stroke:#7C3AED,color:#1F2933
  classDef p5 fill:#FDF1D6,stroke:#B45309,color:#1F2933
  classDef p6 fill:#E1F3E5,stroke:#15803D,color:#1F2933
  classDef p8 fill:#EEEEEE,stroke:#6B7280,color:#1F2933
  classDef ext fill:#FFFFFF,stroke:#9CA3AF,color:#1F2933

  subgraph LEG["Legend: first works in phase"]
    direction LR
    L2["P2 contracts and schema"]:::p2
    L3["P3 wave 1"]:::p3
    L4["P4 wave 2"]:::p4
    L5["P5 memory and gate"]:::p5
    L6["P6 live loop"]:::p6
    L8["P7 to P8 hardening and demo"]:::p8
  end

  subgraph WHO["People"]
    PAT["Patient"]:::ext
    SUP["Supporter"]:::ext
    DOC["Doctor"]:::ext
    DTO["District TB officer"]:::ext
    CHM["Chemist and lab"]:::ext
  end

  subgraph CH["Channels (all optional)"]
    TG["Telegram bot"]:::p4
    GM["Gmail inbound and digests"]:::p5
    CAL["Calendar"]:::p6
    CSV["Chemist CSV"]:::p3
    NK["Mock Ni-kshay"]:::p3
    BAND["Mock band feed (P1)"]:::p8
  end

  subgraph RUN["Google Cloud Run"]
    API["cm-api: REST, webhooks, SSE"]:::p3
    WRK["cm-worker: task handlers"]:::p4
  end

  subgraph Q["Queues"]
    CT["Cloud Tasks: agent-runs, resumes, outbound"]:::p4
    PS["Pub/Sub gmail-push + dead letter"]:::p5
  end

  subgraph BRAIN["Brain: statistics decide, the LLM only explains"]
    ORCH["Deep Agent orchestrator + sub-agents"]:::p5
    REC["Rules R1 to R6 (reconciler)"]:::p3
    MEM["Memory engine: features, beliefs, risk"]:::p5
    NAR["Narrator + cite-or-cut validator"]:::p5
    GATE["Doctor gate: interrupt and resume"]:::p5
  end

  subgraph DATA["Cloud SQL Postgres 16 + pgvector"]
    EV["Event log L0, append-only"]:::p2
    PROJ["Features L1, beliefs L2, cards L3"]:::p5
    APR["approvals, review_decisions"]:::p4
    OUT["outbox (doctor-gate constraint)"]:::p2
    TR["task_runs, heartbeat"]:::p2
    CHK["LangGraph checkpoints and Store"]:::p5
    DOCS["documents, text_chunks (RAG-lite)"]:::p8
  end

  subgraph JOBS["Cloud Run Jobs"]
    NIGHT["cm-nightly"]:::p5
    SWP["cm-sweeper every 5 min"]:::p6
    SEED["cm-seed (mock world)"]:::p3
    EVAL["cm-eval (judge seed)"]:::p8
    MIG["cm-migrate"]:::p2
  end

  subgraph UI["Consoles (React PWA)"]
    DCON["Doctor console: queue, Lens"]:::p6
    DIST["District dashboard"]:::p6
    DEMO["Demo and eval console"]:::p8
  end

  LLM["OpenAI or DeepSeek via init_chat_model"]:::ext

  PAT --> TG
  SUP --> TG
  CHM --> CSV
  DOC --> GM
  TG --> API
  GM --> PS --> API
  CSV --> API
  NK --> API
  BAND --> API
  API -->|"ack in under 1 s"| CT --> WRK
  WRK --> ORCH
  ORCH --> REC
  ORCH --> MEM
  ORCH --> NAR
  NAR --> LLM
  ORCH --> LLM
  API --> EV
  REC --> EV
  MEM --> PROJ
  EV --> MEM
  NAR --> GATE --> APR
  APR -->|"decide() writes outbox in one transaction"| OUT
  OUT -->|"drainer"| TG
  OUT --> GM
  OUT --> CAL
  ORCH --- CHK
  WRK --> TR
  NIGHT --> ORCH
  SWP --> TR
  SEED --> EV
  EVAL --> MEM
  MIG --> DATA
  API --> DCON
  API --> DIST
  API --> DEMO
  DOC --> DCON
  DTO --> DIST
```

---

## 2. The 10 phases and the approval gates

Each phase is explained to you, you approve it, then it runs. Nothing moves on until its exit gate passes.

```mermaid
flowchart LR
  P0["Phase 0<br/>Pre-flight<br/>tonight"] --> G0{"Keys, accounts,<br/>scaffold-v0"}
  G0 --> P1["Phase 1<br/>Lock and go/no-go<br/>H0 to 0:30"]
  P1 --> P2["Phase 2<br/>Contract freeze<br/>H0:30 to 2:30"]
  P2 --> G2{"contracts-v1 tag,<br/>14 worktrees"}
  G2 --> P3["Phase 3<br/>Wave 1 build<br/>H2:30 to 6"]
  P3 --> M1{"Merge 1 at H6"}
  M1 --> P4["Phase 4<br/>Wave 2 build<br/>H6 to 10"]
  P4 --> C10{"Merge 2 and<br/>cut check H10"}
  C10 --> P5["Phase 5<br/>Memory, narrator, gate<br/>H10 to 14"]
  P5 --> C14{"Merge 3 and<br/>cut check H14"}
  C14 --> P6["Phase 6<br/>Live Ravi loop on GCP<br/>H14 to 18"]
  P6 --> P7["Phase 7<br/>Hardening<br/>H18 to 22"]
  P7 --> F22{"Feature freeze H22"}
  F22 --> P8["Phase 8<br/>Demo lock<br/>H22 to 30"]
  P8 --> V30{"Backup video H30"}
  V30 --> P9["Phase 9<br/>Rehearse and demo<br/>H30 to 36"]
  P9 --> D32{"No deploys<br/>after H32"}
```

### Timeline (clock time assumes a 10:00 start)

```mermaid
gantt
  title CareMemory build phases (H0 = 10:00 Sat 24 Oct, assumed)
  dateFormat YYYY-MM-DD HH:mm
  axisFormat %a %H:%M
  section Phases
  P0 Pre-flight (tonight)          :p0, 2026-10-23 20:00, 2026-10-24 10:00
  P1 Lock and go/no-go             :p1, 2026-10-24 10:00, 2026-10-24 10:30
  P2 Contract freeze               :crit, p2, 2026-10-24 10:30, 2026-10-24 12:30
  P3 Wave 1 build                  :p3, 2026-10-24 12:30, 2026-10-24 16:00
  P4 Wave 2 build                  :p4, 2026-10-24 16:00, 2026-10-24 20:00
  P5 Memory, narrator and gate     :crit, p5, 2026-10-24 20:00, 2026-10-25 00:00
  P6 Live Ravi loop on GCP         :crit, p6, 2026-10-25 00:00, 2026-10-25 04:00
  P7 Hardening                     :p7, 2026-10-25 04:00, 2026-10-25 08:00
  P8 Demo lock                     :p8, 2026-10-25 08:00, 2026-10-25 16:00
  P9 Rehearse and final demo       :p9, 2026-10-25 16:00, 2026-10-25 22:00
  section Checkpoints
  contracts-v1 tag (H2:30)         :milestone, m1, 2026-10-24 12:30, 0m
  Merge 1 (H6)                     :milestone, m2, 2026-10-24 16:00, 0m
  Cut check and merge 2 (H10)      :milestone, m3, 2026-10-24 20:00, 0m
  Cut check and merge 3 (H14)      :milestone, m4, 2026-10-25 00:00, 0m
  Feature freeze (H22)             :milestone, m5, 2026-10-25 08:00, 0m
  Backup video (H30)               :milestone, m6, 2026-10-25 16:00, 0m
```

---

## 3. Which agent builds what (14 lanes plus Opus)

Each lane edits only its own folders (`scripts/check_ownership.py` enforces it). Contracts are frozen, so lanes never wait on each other: each builds against fakes.

```mermaid
flowchart TB
  classDef opus fill:#F3E8FF,stroke:#7C3AED,color:#1F2933
  classDef son fill:#E3EEF9,stroke:#2563EB,color:#1F2933
  classDef hai fill:#E1F3E5,stroke:#15803D,color:#1F2933

  subgraph FOUND["Foundation"]
    L0["L0 Contracts and schema<br/>Opus, 4 h"]:::opus
    A["A Data core: events, repos, clock<br/>Sonnet, 11 h"]:::son
    I["I Infra, Docker, deploy scripts<br/>Haiku plus owner, 7.5 h"]:::hai
  end

  subgraph ENG["Engines"]
    C["C Memory engine: features, beliefs, risk<br/>Sonnet, 12.5 h"]:::son
    D["D Rules R1 to R6, validator, identity<br/>Sonnet, 9.5 h"]:::son
    E["E Runtime, doctor gate, tools<br/>Sonnet, 10 h"]:::son
    N["N Narrator and sub-agents<br/>Sonnet, 9 h"]:::son
  end

  subgraph CHAN["Channels and content"]
    F["F Telegram, Supporter, router, household<br/>Sonnet, 16.5 h"]:::son
    M["M Gmail, consent, calendar<br/>Sonnet, 11.5 h"]:::son
    K["K Templates, mock feeds, guideline seed<br/>Haiku, 8.5 h"]:::hai
  end

  subgraph IFACE["Interfaces"]
    G["G Core API and decide()<br/>Sonnet, 12.5 h"]:::son
    B["B Mock world generator, console backend<br/>Sonnet, 12.5 h"]:::son
    H1["H1 Doctor console, queue, Lens<br/>Sonnet, 19.5 h"]:::son
    H2["H2 District, demo, admin screens<br/>Haiku, 14 h"]:::hai
  end

  subgraph QUAL["Quality"]
    J["J Evaluation, replay, offline demo<br/>Haiku, 10.5 h"]:::hai
    INT["Integration: merges and tests<br/>Opus, 8 plus h"]:::opus
  end

  L0 --> A
  L0 --> G
  L0 --> H1
  A --> C
  A --> E
  A --> B
  C --> N
  D --> N
  D --> E
  G --> H1
  H1 --> H2
  B --> J
  C --> J
  A --> F
  A --> M
  F --> INT
  M --> INT
  N --> INT
  E --> INT
  H1 --> INT
  J --> INT
```

Total about 166 agent-hours plus about 12 Opus hours, which fits 14 lanes × 19.5 h (about 79% utilised with a 1.3× overrun).

### Lane timeline (same clock)

```mermaid
gantt
  title Lane windows (H2.5 = 12:30 Sat)
  dateFormat YYYY-MM-DD HH:mm
  axisFormat %a %H:%M
  section Opus
  L0 contracts (tier 1 H2.5, tier 2 H4)  :crit, l0, 2026-10-24 10:00, 2026-10-24 14:00
  Integration (merges, Ravi loop)         :crit, int, 2026-10-24 16:00, 2026-10-25 08:00
  section Foundation
  A Data core                              :crit, a, 2026-10-24 12:30, 2026-10-24 17:00
  A rest of core (to H13)                  :a2, 2026-10-24 17:00, 2026-10-24 23:00
  I Infra and deploy skeleton              :i, 2026-10-24 10:30, 2026-10-24 18:00
  section Engines
  C Memory engine                          :crit, c, 2026-10-24 13:00, 2026-10-25 02:00
  D Rules, validator, identity             :d, 2026-10-24 12:30, 2026-10-24 23:00
  E Runtime, gate, tools                   :crit, e, 2026-10-24 13:00, 2026-10-25 03:00
  N Narrator and sub-agents                :crit, n, 2026-10-24 13:00, 2026-10-25 02:00
  section Channels
  F Telegram, Supporter, router            :f, 2026-10-24 12:30, 2026-10-25 05:00
  M Gmail, consent, calendar               :m, 2026-10-24 12:30, 2026-10-25 01:00
  K Content, mock feeds                    :k, 2026-10-24 12:30, 2026-10-24 22:00
  section Interfaces
  G Core API                               :crit, g, 2026-10-24 12:30, 2026-10-25 03:00
  B Generator then console backend         :b, 2026-10-24 12:30, 2026-10-25 02:00
  H1 Doctor console                        :crit, h1, 2026-10-24 12:30, 2026-10-25 08:00
  H2 District, demo, admin                 :h2, 2026-10-24 14:00, 2026-10-25 06:00
  section Quality
  J Evaluation and replay                  :j, 2026-10-24 13:00, 2026-10-25 04:00
```

---

## 4. How the dependencies run (critical path in red)

The critical path is about 20.5 hours, with about 1.5 hours of slack before the H22 freeze.

```mermaid
flowchart LR
  classDef crit fill:#FBEAEA,stroke:#B91C1C,color:#1F2933
  classDef norm fill:#FFFFFF,stroke:#9CA3AF,color:#1F2933

  L0["L0 contracts<br/>2.5 h"]:::crit --> AQ["A: query, append, repos<br/>to H7"]:::crit
  AQ --> CM["C: detectors, risk, intervals<br/>to H14"]:::crit
  CM --> NE["N narrator on real L2<br/>E interrupt, decide, resume<br/>to H17"]:::crit
  NE --> WIRE["G and H1 wire queue and Lens<br/>to H18:30"]:::crit
  WIRE --> LIVE["Ravi day-60 loop on Cloud Run<br/>to H20:30"]:::crit
  LIVE --> FRZ["Feature freeze H22"]:::crit

  L0 --> GS["G route stubs, openapi.json<br/>H4"]:::norm
  GS --> H1S["H1 builds screens on fixtures"]:::norm
  H1S --> WIRE
  AQ --> BF["B fixtures H5, seed job H10"]:::norm
  BF --> CM
  AQ --> DR["D rules on events"]:::norm
  DR --> NE
```

If lane C slips past H14, lanes N and H1 keep working on the Ravi fixture snapshots, C lands by H17, and Integration absorbs it.

---

## 5. How a task becomes work: the Deep Agent orchestrator

Every incoming task (a Telegram tap, a Gmail reply, the nightly rebuild, an evaluation) becomes a standard envelope. Simple, known tasks skip the AI entirely.

```mermaid
flowchart TB
  classDef det fill:#E6F4F1,stroke:#0F766E,color:#1F2933
  classDef ai fill:#EDE7F6,stroke:#7C3AED,color:#1F2933
  classDef human fill:#FDF1D6,stroke:#B45309,color:#1F2933

  IN["Task arrives: tap, email, CSV, nightly, eval"] --> ENV["TaskEnvelope with task_id"]
  ENV --> DISP{"dispatch()"}
  DISP -->|"button tap, known CSV, red symptom"| FAST["Plain code fast path<br/>no LLM"]:::det
  DISP -->|"everything else"| ORCH["Deep Agent orchestrator<br/>plans with write_todos"]:::ai

  subgraph SUBS["Sub-agents the orchestrator can call"]
    INT["intake: parse messages and files"]:::ai
    IDN["identity: match to the right patient"]:::det
    CUR["memory-curator: update the memory"]:::ai
    INV["investigator: multi-step patterns (P1)"]:::ai
    NAR["narrator: write the cited card"]:::ai
    DRA["drafter: messages for patient, Supporter, doctor"]:::ai
  end

  ORCH --> INT
  ORCH --> IDN
  ORCH --> CUR
  ORCH --> INV
  ORCH --> NAR
  ORCH --> DRA

  subgraph TOOLS["Governed tools (read-only by default)"]
    T1["patient snapshot, as_of reads"]:::det
    T2["detectors and risk score"]:::det
    T3["rules R1 to R6"]:::det
    T4["submit_for_review, send_message"]:::human
  end

  CUR --> T1
  INV --> T2
  CUR --> T3
  NAR --> VAL["Cite-or-cut validator<br/>number check, cut uncited, template fallback"]:::det
  VAL --> T4
  DRA --> T4
  T4 --> GATE["Doctor gate: graph pauses at interrupt()"]:::human
  GATE --> APR["approvals row, doctor decides"]:::human
  APR --> DEC["review_service.decide()<br/>one transaction: decision plus outbox rows"]:::det
  DEC --> SEND["Outbox drainer sends"]:::det
  DEC -->|"resume with Command"| ORCH
```

---

## 6. One approval from start to finish

```mermaid
sequenceDiagram
  autonumber
  participant SCH as Cloud Scheduler
  participant NIT as cm-nightly
  participant MEM as Memory engine
  participant AG as Orchestrator and narrator
  participant DB as Postgres
  participant DOC as Doctor (console or Gmail)
  participant OB as Outbox drainer
  participant SUP as Supporter on Telegram

  SCH->>NIT: 01:00 run
  NIT->>MEM: rebuild beliefs and risk as_of yesterday
  MEM->>DB: write features, beliefs, conflicts
  NIT->>AG: prepare card and visit list
  AG->>AG: draft, then cite-or-cut check
  AG->>DB: upsert approvals row, then interrupt
  DOC->>DB: open queue, see evidence first
  DOC->>DB: approve (decide() in one transaction)
  DB->>DB: write review_decision and outbox rows
  DB-->>AG: resume task on the same thread_id
  OB->>SUP: send approved visit brief
  SUP->>DB: tap Witnessed (event, then memory)
```

---

## 7. Phase by phase: goal, agents, output, gate

| Phase | Hours | Goal | Agents that run | Output | Exit gate |
|---|---|---|---|---|---|
| **0 Pre-flight** | tonight | Accounts, keys, repo ready | Coordinator (Sonnet), you | `.env`, GCP project, bots, `scaffold-v0` commit | Keys work, spend caps set, organiser check done |
| **1 Lock and go/no-go** | H0 to 0:30 | Confirm the plan is allowed and still right | Coordinator, Opus L0 starts | A go decision | You approve |
| **2 Contract freeze** | H0:30 to 2:30 | Freeze schemas and tables so lanes can run in parallel | **Opus L0**, Haiku I | `contracts-v1`, golden fixtures, 14 worktrees, ownership hook | `make contracts-check` green, tag exists |
| **3 Wave 1** | H2:30 to 6 | Foundations built against fakes | Up to 11 Sonnet and 2 Haiku: A, B, D, K, G, F, M, H1, H2, I, J | Event store and repos, mock-world generator, rules, templates, API stubs (`contracts-v1.1` at H4), first screens | Merge 1 at H6: seed runs on Cloud SQL, skeleton `cm-api` and `cm-worker` deployed |
| **4 Wave 2** | H6 to 10 | Channels, review service, console backend | Same lanes, plus B phase 2 | Telegram flow, `decide()`, outbox drainer, Gmail parse, consent, identity | Merge 2 at H10, then cut check |
| **5 Memory, narrator, gate** | H10 to 14 | The brain works on the real store | C, N, E (Opus reviews resume), Integration | Memory engine, risk with intervals, narrator and validator, orchestrator, nightly job | Merge 3 at H14, then cut check; Ravi day-3 and day-60 snapshots match fixtures |
| **6 Live Ravi loop on GCP** | H14 to 18 | One real loop from tap to approval to send | Integration (Opus), G, H1, E, F, M | Queue and Lens wired live, SSE, sweeper, district dashboard | Ravi day-60 loop passes end to end on Cloud Run |
| **7 Hardening** | H18 to 22 | Errors, edge cases, polish | All lanes in fix mode | Reliability tests, red-team tests, error states | **Feature freeze at H22** |
| **8 Demo lock** | H22 to 30 | Make the demo unbreakable | Integration, J, K | Fixed evaluation seeds, recorded-answer cassette, offline drill, twin accounts if P1 survived, backup video | Backup video by H30 |
| **9 Rehearse and final demo** | H30 to 36 | Practise and present | You, coordinator | Rehearsals, Q&A drill | No deploys after H32 |

### Cut list (pre-approved, applied at H10 and H14 in this order)
1. Channel kill switches and what-if view. 2. Timeline tab. 3. Charts tab. 4. Admin users page. 5. Escalation fast-forward. 6. Live updates (fall back to 5 s polling). 7. Supporter number replies. 8. Minimal household wizard.

**Never cut:** Memory Lens, review queue and doctor gate, cite-or-cut, Telegram check-in, rules R1 to R6, household screening with its KPI, the evaluation re-roll, offline replay.

### Usage-limit rule
The number of agents running drops as your usage meter rises (11, then 8, 5, 2). Agents keep a RESUME POINT in their `NOTES.md` and commit often. After a reset, resume them with a message.

---

## 8. What every agent receives (the context pack)

1. **Lane brief:** its folders, the spec section it implements, its start and finish hours, and what it depends on.
2. **Read first:** `caremem/MEMORY.md` (standing rules), `caremem/CLAUDE.md` (rules and lane table), `INTEGRATION_DECISIONS.md`, then its feature spec.
3. **Contracts and fixtures:** `cm/contracts/` (frozen), golden fixtures, and a fake for every dependency.
4. **OpenSpec duty (MEMORY.md Rule 1):** open a change, write the tasks, build, validate, archive. Bug fixes use `skip_specs: true`.
5. **Definition of done:** `make check` is green, its fakes exist, fixtures updated only through an RFC, and a short `NOTES.md` in its folder with a RESUME POINT.
6. **Stuck for more than 20 minutes:** write the blocker, stub with the fixture, and move on. Never redesign contracts.
7. **Never:** edit outside the lane, edit frozen contracts, put secrets in files, or commit or push unless the owner says so.
