# CareMemory: patient-memory RAG strategy v2

As of 2026-10-24. Read-only research output; no code, contract or migration was changed.
Builds on `RAG_MEMORY_DESIGN.md` (v1) and `INTEGRATION_DECISIONS.md` T6 / C12 / C13. Where this
document departs from v1 or a frozen contract, it says so and proposes an RFC. Claims not checked
against running code or a provider page are marked **UNVERIFIED**.

Goal from the owner: from day one, collect every patient signal (Telegram taps and messages, Gmail
digests and replies, web app events, uploaded documents, chemist refill CSV, doctor notes), turn it into
chunks + embeddings in Postgres pgvector, and answer questions with top-k hybrid retrieval (BM25 +
vector, RRF, MMR, optional rerank), per-patient isolation, `as_of` filtering and cite-or-cut citations.

---

## 1. What exists vs what is missing

| Area | Exists today (file) | State | Missing |
|---|---|---|---|
| Event log (source of truth) | `cm/store/migrations/0001_core.sql` `cm.events` (append-only trigger, `occurred_at`, `recorded_at`, `consent_id`, `supersedes`, `idempotency_key`, `sim_run_id`) | Done, frozen | Nothing; RAG reads from it |
| Document + chunk tables | `0004_rag.sql`: `cm.documents`, `cm.text_chunks` (`halfvec(1536)`, HNSW m=16/ef=64, guideline partial HNSW, generated `tsv` with `'simple'` config, GIN, filter index `(patient_token, doc_type, occurred_at DESC) WHERE status='active'`), `cm.guideline_chunks` view | Done, frozen (contracts-v1) | `doc_type` CHECK has only 7 values (no message, doctor_note, summary, event); no `chunk_kind`, no window columns, no bitemporal validity (`valid_to`), no `source_event_ids` |
| pgvector locally | `docker-compose.yml` uses `pgvector/pgvector:pg16` | Done | Cloud SQL `extversion >= 0.7` still **UNVERIFIED** (cm-migrate asserts) |
| Embedding role | `cm/core/llm.py`: role `EMBEDDING`, OpenAI-only, `init_embeddings(spec)`, `embed_documents` through the governor; budget template-only mode does not block embeddings | Code done | **Off in this checkout**: `EMBEDDING_MODEL` is empty in `.env` and no OpenAI key is set (checked by presence only, values not read). `.env.example` says empty = Postgres full-text fallback |
| PII guard | `cm/core/tokenize.py` `tokenize()` (email, phone, Aadhaar, ids, titled names, registered names) and `assert_clean()` in `llm.py` | Done | Tokens are stable only within one call (`[PHONE_1]`), so chunk text must be tokenized once at index time and stored tokenized |
| Chunker / seed | `cm/rag/chunk.py`, `cm/rag/seed.py` | Skeletons (`NotImplementedError`) | All chunking, rendering, embedding, indexing |
| Guideline search tool | `cm/tools/guidelines.py` `search_guidelines` | Skeleton | Whole retrieval pipeline |
| Patient memory tool | none | Missing | `search_patient_memory` tool |
| Agent tools | `cm/tools/readonly.py`: `get_patient_snapshot`, `list_events`, `compute_features` over `RunContext.events` (in-memory, already `as_of`-cut) | Done | A retrieval tool in the same `governed()` wrapper |
| Narrator | `cm/agents/narrator.py`: features-only prompt, JSON sentences, `cite_or_cut`, banned terms, template fallback | Done | Optional D-chunk context (P1, see 5.3) |
| Cite-or-cut | `cm/validator/cite_or_cut.py`: regex `[EBCRGD]-id`, cuts no-ref / unknown-ref / number not in evidence | Done, already accepts `D-` refs | Evidence builder for D refs; per-sentence (local) number check |
| Ask box | `cm/api/routers/query.py`: canned regex answers + WORKER tool loop (`list_patients`, `get_patient`, `list_pending_approvals`), `[n]` markers, `verify_numbers` | Done (list-level only) | Patient-level free-text questions; retrieval tool; abstain path |
| as_of | `cm/store/as_of.py` `filter_as_of` | Skeleton (Rule 9 says use `cm.store.as_of.query`) | SQL `as_of` predicate for chunks |
| Ingest route | `cm/api/routers/ingest.py` | Empty skeleton | Upload, classify, extract, write events + documents, enqueue indexing |
| Sim + eval | `cm/sim/gen.py` (seeded patients, patterns `market_day`, `payday`, `over_reporter`, `drift`), `cm/sim/truth.py`, `cm/eval/harness.py` (Day 3 vs Day 60 risk eval), `cm/eval/metrics.py` (Brier, AUROC, ECE) | Done for risk | Retrieval metrics (recall@k, MRR, nDCG), gold-chunk builder, answer-level eval |
| Seed data | `cm/jobs/seed_events.py` (PT-0142 has 60 days of dose history, notes, documents as `ContextNote{kind:'document'|'medicine'|'summary'}`), `fixtures/text_bank.json` | Done | A 3-day demo patient with the same channels |
| OpenSpec | `openspec/changes/`: gcp deploy, memory engine v1, real Gmail, rules R1-R6. No RAG change | n/a | `add-patient-memory-rag` change (MEMORY.md Rule 1) |
| Scope ruling | INTEGRATION_DECISIONS T6: P0 = DDL + guideline seed; P1 = `search_guidelines` + patient prose chunks; v1's SQL-generation tool rejected | Binding | Owner must explicitly pull patient RAG into scope (decision D1) |

Identifier note: the DB token is `P-0042` (`patient_token ~ '^P-[0-9]{4}$'`); the UI shows `PT-0142`
(`display_code`). The retrieval tool must take the UI code, resolve it server-side, and never let the
model choose a token.

---

## 2. Chunking strategy per source

Principles:
1. **Events are the truth; chunks are a rebuildable search index over them.** Every chunk carries the
   `event_id`s it was rendered from, so an answer can cite `E-` ids as well as `D-` ids.
2. **Render, don't dump.** Structured events become one deterministic sentence by a template
   (no LLM), e.g. `2026-02-03 Tue, Telegram, patient: dose not taken. Reason given: "went to the market".`
   Numbers in a chunk come from the event payload or from `cm/memory` features, never from an LLM.
3. **Tokenize before storing and before embedding.** `content` holds tokenized text; raw text stays in
   `events.payload` / GCS.
4. **Three granularities** so both short and long histories retrieve well: event chunks (precision),
   daily rollups (one per patient-day), weekly rollups (pattern questions). Long free text gets sliding
   windows; documents get structure-aware chunks with a parent.

| # | Source | Unit | chunk_kind | Target size | Overlap | Rationale |
|---|---|---|---|---|---|---|
| 1 | Telegram tap (`DoseCheckin`, quick replies) | 1 event = 1 chunk | `event` | 15-40 tokens | none | Atomic facts; perfect precision; citation maps 1:1 to an `E-` id. Embed only if a free-text reason exists, otherwise FTS-only (`embedding NULL`) to save cost |
| 2 | Telegram free-text messages (patient, Supporter) | short (< 120 tokens): 1 message = 1 chunk; conversations: sliding window of 6 consecutive messages in one thread within 24 h | `event` / `window` | window cap 256 tokens | 2 messages (about 33%) | Meaning spans turns ("why?" / "had fever"); 2-message overlap keeps a question with its answer in at least one window |
| 3 | Web app events (portal dose mark, undo, record, requests) | 1 event = 1 chunk; `undone` marks render as "dose mark withdrawn" and supersede | `event` | 15-60 tokens | none | Same as taps; supersede keeps retrieval honest |
| 4 | Gmail digests (outbound, approved) | 1 digest = 1 chunk, author `system` | `event` | up to 400 tokens | none | Tells the model what the doctor was already told; lower prior in ranking (0.5 weight) so it never outranks primary evidence |
| 5 | Gmail doctor replies | body under 400 tokens: 1 chunk; longer: 300-token windows | `event` / `window` | 300 | 50 (about 17%) | v1 rule; quoted history stripped before chunking (dedup by `content_hash`) |
| 6 | Doctor notes (console `ContextNote`, review decision reasons) | paragraph-aware; 1 chunk if under 500 tokens, else split on paragraphs to 400 | `doc` | 400 | 60 (15%) | Clinical prose; parent = whole note (cap 1,500) for answer context |
| 7 | Prescription (upload) | structured fields go to events (never embedded); free-text instructions = 1 chunk | `doc` | up to 400 | none | v1 rule; drug names must not reach patient-facing text, so this doc type is `sensitivity` checked and doctor-audience only |
| 8 | Lab report (upload) | values to `LabResult` events; remarks/impression = 1 chunk; plus one rendered "lab summary" sentence per report (test, flag high/normal/low, date; no raw value table) | `doc` + `event` | up to 300 | none | Lets "what did the lab say" retrieve, while numbers stay in events. Digit-ratio guard (40%) rejects tables |
| 9 | Long PDFs (discharge summary, guideline) | heading-aware, then recursive split | `doc` (child) + parent | child 400, parent up to 1,500 | 60 (15%) | Child for search precision, parent for answer context; heading path in `extra.section` |
| 10 | Chemist refill CSV | rows never embedded; one rendered `Dispense` sentence per refill ("refill of 28-day supply recorded at chemist") + weekly refill line inside the weekly rollup | `event` | 20-40 | none | Questions like "when did she last pick up medicine" need a text hit; the number comes from the event |
| 11 | Daily rollup (built nightly per patient-day, deterministic from `cm/memory`) | 1 per patient-day | `daily` | 60-150 | none (days are disjoint) | Gives the 30-day patient compact, rankable day records; cheap (30 chunks/month) |
| 12 | Weekly rollup (Mon-Sun, deterministic from features: missed count, top miss weekday, refill gap, quiet days, notable quotes by id) | 1 per patient-week | `weekly` | 150-300 | 3-day overlap is NOT used; weeks are disjoint, the daily layer covers boundaries | Pattern questions ("does she miss on market days?") match one weekly chunk instead of 7 scattered events |
| 13 | Guidelines (domain, `patient_token NULL`) | v1 rule: heading-aware 300-500 tokens, contextual prefix | `doc` | 400 | 50 | Unchanged from v1 / T6 |

Why these sizes: per-patient corpora are small (estimate for a 30-day patient: about 120 event chunks
+ 30 daily + 5 weekly + 5-10 doc chunks, about 170 chunks, about 12K tokens), so the risk is not scale
but **dilution** (a long chunk mixing many days ranks for everything). Small atomic chunks plus
rollups give precision and coverage; overlap is used only where sentences genuinely span units
(conversations, long prose). Sizes are starting points; the eval (section 6) ablates
event-only vs event+rollups.

Rollup text must not contain disease or drug names (Rule 5) and carries its numbers only as
feature references, e.g. `Week of 2026-02-02: 2 doses not taken, both on Tuesday [B-weekday_pattern].`

---

## 3. Metadata schema and migration changes

### 3.1 What the frozen DDL already gives us (use as-is)

`patient_token`, `doc_type`, `status`, `occurred_at`, `recorded_at`, `consent_id`, `language`,
`sensitivity`, `content`, `content_hash`, `embedding halfvec(1536)`, `embedding_model`, generated
`tsv`, `parent_id`, `document_id` (NOT NULL FK), `extra jsonb`. One `documents` row is needed per
chunk source; for events use one synthetic `documents` row per (patient, source event or window) with
`source` = channel and `extraction_model = 'render-v1'`.

### 3.2 Gaps, and two ways to close them

| Gap | Option A: no RFC (demo tonight) | Option B: RFC (clean) |
|---|---|---|
| `doc_type` lacks message / doctor_note / summary / event kinds | Map onto existing values: Telegram/web events and windows -> `checkin`; Gmail digest/reply -> `email`; doctor note -> `supporter_note` with `author_role='doctor'`; rollups -> `checkin` with `author_role='system'`. Real kind in `extra.chunk_kind` | **RFC-R1**: widen both CHECKs to add `message`, `doctor_note`, `rollup`, `event` |
| chunk granularity | `extra.chunk_kind` in (`event`,`window`,`daily`,`weekly`,`doc`) | **RFC-R2**: column `chunk_kind text NOT NULL DEFAULT 'doc'` + index `(patient_token, chunk_kind, occurred_at DESC) WHERE status='active'` |
| link back to events (for `E-` citations and erasure) | `extra.source_event_ids` (uuid list as JSON) | **RFC-R2**: `source_event_ids uuid[] NOT NULL DEFAULT '{}'` + GIN |
| rollup windows | `extra.window_start`, `extra.window_end` | **RFC-R2**: `window_start timestamptz`, `window_end timestamptz` |
| bitemporal correctness for rebuilt rollups (a late event re-renders day 12 on day 14; a query `as_of` day 13 must still see the old day-12 rollup) | Rebuild rollups only at window close, never revise; late events appear only as event chunks | **RFC-R3**: `valid_to timestamptz NULL` (set when superseded). Filter becomes `recorded_at <= as_of AND (valid_to IS NULL OR valid_to > as_of)` instead of `status='active'` for replays |
| short `D-` citation id | derive in code: `D-` + first 8 hex of `chunk_id` (same rule as `cite_id` for events); look up by prefix | none needed |
| embedding off / cost | `embedding NULL` allowed by the DDL (CHECK only ties it to `embedding_model`) | none |
| sim runs | `extra.sim_run_id` | RFC-R2 optional `sim_run_id uuid` (mirrors `events.sim_run_id`) |

Recommendation: **Option A for tomorrow's demo** (all additive in code, zero contract risk), and file
RFC-R1..R3 now so the clean schema lands as additive migration `0009_rag_v2.sql` (lane A) after the
demo. Note 0004's header comment says refs are `[D:chunk_id]` while `cite_or_cut.CITE` matches `D-id`;
T6 text also says `[D:...]`. Code wins: use `[D-xxxxxxxx]`; mention it in the RFC.

### 3.3 RFC text to append to `cm/contracts/CHANGES.md` (L0 owns the file; proposal only)

```
## RFC-R1 (lane A/K): widen RAG doc_type
documents.doc_type and text_chunks.doc_type CHECK add 'message','doctor_note','rollup','event'.
Additive (no existing value removed). Migration 0009_rag_v2.sql drops and re-adds both CHECKs.

## RFC-R2 (lane A/K/N): chunk granularity columns on text_chunks
chunk_kind text NOT NULL DEFAULT 'doc' CHECK (chunk_kind IN ('event','window','daily','weekly','doc')),
source_event_ids uuid[] NOT NULL DEFAULT '{}', window_start timestamptz, window_end timestamptz,
sim_run_id uuid. Indexes: (patient_token, chunk_kind, occurred_at DESC) WHERE status='active';
GIN(source_event_ids). Citation ref for chunks is [D-<8 hex of chunk_id>] (matches cite_or_cut.CITE).

## RFC-R3 (lane A): bitemporal validity for rebuilt chunks
valid_to timestamptz NULL; superseding a chunk sets valid_to = recorded_at of the new chunk.
as_of retrieval predicate: recorded_at <= :as_of AND occurred_at <= :as_of
AND (valid_to IS NULL OR valid_to > :as_of) AND status <> 'withdrawn'.
```

### 3.4 Isolation and consent columns in the query (both options)

Every retrieval runs inside `cm/store` SQL (Rule 6) with:
`patient_token = :tok` (injected by the tool wrapper from the resolved UI code), `doc_type <> 'guideline'`,
`status <> 'withdrawn'`, the `as_of` predicate above, a join or `NOT EXISTS` on withdrawn consents
(`consent_id`), and `sensitivity = ANY(:allowed_for_audience)` (doctor: all; Supporter/patient: `normal`).
Per-patient sets are tiny, so the vector leg is an **exact** scan on the filtered rows (perfect recall,
no HNSW post-filter starvation). If HNSW is used later, `SET LOCAL hnsw.iterative_scan = relaxed_order`
(pgvector >= 0.8, **UNVERIFIED** on Cloud SQL).

---

## 4. Retrieval pipeline

`route -> resolve patient -> rewrite -> prefilter -> two legs -> RRF -> boosts -> (rerank) -> MMR -> assemble -> generate -> cite-or-cut -> abstain or answer`

| Step | Design | Parameters (start values) |
|---|---|---|
| 0 Route | Ask box keeps its canned/regex + WORKER tool loop. Numeric questions use `compute_features` / existing tools (numbers only from `cm/memory`). Free-text "why / what did / when did X say" questions call `search_patient_memory`. The model may call both | max 4 tool steps (existing `MAX_STEPS`) |
| 1 Resolve | `PT-xxxx` from the question or page context -> `patient_token` server-side; role scope check (doctor sees own clinic) | reject if unresolved |
| 2 Rewrite | `tokenize(question)`; deterministic Hinglish/Telugu synonym expansion for the lexical leg only (small dictionary in `cm/rag/lexicon.py`, e.g. "missed" ~ "nahi li", "market" ~ "bazaar"); parse time phrases ("last week", "since Monday", "day 12") to a window filter | no LLM call |
| 3 Prefilter | Section 3.4 predicate; optional window filter from step 2 | candidate pool = all of the patient's live chunks (about 30 for 3-day, about 170 for 30-day) |
| 4a Vector leg | cosine on `embedding` (query embedded via `get_model("EMBEDDING")`, tokenized text) | top 40 |
| 4b Lexical leg | **Real BM25 in Python** over the prefiltered pool (`rank_bm25`, k1=1.2, b=0.75) because Postgres `ts_rank_cd` is not BM25 and ParadeDB is unlikely on Cloud SQL. Fallback when the dependency is refused: `tsv @@ websearch_to_tsquery('simple', q)` ranked by `ts_rank_cd` | top 40 |
| 5 Fuse | RRF: `score = sum_legs w_leg / (60 + rank)`; `w_vec = 1.0`, `w_lex = 1.0`. If embeddings are off, the vector leg is skipped and the pipeline still works (FTS/BM25-only mode) | k = 60 |
| 6 Boosts | multiply by kind prior (`weekly` 1.15 for pattern questions detected by keywords "usually, pattern, always, which day"; outbound digest 0.5) and recency `1 + 0.1 * exp(-age_days / 14)` | small, so evidence still dominates |
| 7 Rerank (flag `RAG_RERANK`) | `none` (default) / `llm` (WORKER listwise rerank of top 20 -> top 8; one tokenized call, through the governor) / `cross_encoder` (local `bge-reranker-v2-m3`, about 2 GB image growth, CPU latency **UNVERIFIED**). Cohere is excluded: runtime providers are OpenAI or DeepSeek only (Rule 16) | top 20 in, top 8 out |
| 8 MMR | on the fused list, lambda 0.7, cosine between chunk embeddings (Jaccard on tokens when embeddings are off); max 3 chunks per calendar day; drop a child when its parent or its daily rollup already covers the same `source_event_ids` | final k = 8 |
| 9 Assemble | each chunk as `[D-1a2b3c4d] 2026-02-03 Tue | telegram | patient | text` plus `also: [E-...]` for its `source_event_ids`; parent expansion for `doc` children; token budget 1,800 | ordered by date ascending (timelines read better) |
| 10 Generate | WORKER model (Ask) or ORCHESTRATOR (narrator); JSON `{"sentences": [...]}`; every sentence ends with `[D-..]` and/or `[E-..]`/`[B-..]`; no advice, no diagnosis | temperature 0 |
| 11 Cite-or-cut | `Evidence.of(valid_ids = retrieved D ids + their E ids + feature B ids, numbers = numbers in the cited chunks' events + features)` then `cite_or_cut`. Add a stricter local check (lane D): a number must appear in a chunk the same sentence cites | cut_ratio logged |
| 12 Abstain | if top fused score is below a threshold, or nothing survives cite-or-cut: answer "Not in the record up to <as_of date>." and list the top 3 nearest sources | threshold tuned on the eval set |
| 13 Cache | key `hash(patient_token, normalised question, as_of day, data_version)`; Postgres table (no Redis) | TTL 24 h |

`as_of`: the Ask box today uses `now()` from `cm.api.deps` (sim clock). The retrieval tool receives
that instant and applies the RFC-R3 predicate (or, under Option A, `recorded_at <= as_of AND
occurred_at <= as_of AND status <> 'withdrawn'`). In the sim, `recorded_at` is the sim instant, so a
day-3 replay of the 30-day patient can never see day 4+ chunks. Test it (section 6.4).

---

## 5. How it plugs into cite-or-cut, the Ask box and the narrator

### 5.1 Tool
New `cm/tools/memory_search.py` (lane N; needs an L0 entry in `scripts/lanes.yaml`) exposing
`search_patient_memory(code: str, question: str, k: int = 8) -> list[ChunkHit]`.
It calls `cm/store/chunks_repo.py` (lane A) for SQL and does fusion/MMR/rerank in Python. It is wrapped by
`governed()` from `cm/tools/readonly.py` (breaker, tokenize-on-the-way-out, banned-term check for
patient-facing audiences). `ChunkHit = {ref: "D-xxxxxxxx", date, source, author_role, kind, text,
event_refs: ["E-..."], score}`.

### 5.2 Ask box (`cm/api/routers/query.py`, lane G)
- Add `search_patient_memory` to `_tools()` in the LLM path; its output goes through the existing
  `finish()` so it gets a `[n]` marker and lands in `tool_calls_used[].result_preview` with the `D-`
  refs and dates. **No contract change**: `ToolCallUsed` already carries `result_preview: list[dict]`.
- Change the system prompt to ask for `[n]` after each fact **and** the `D-`/`E-` ref inside the
  sentence; run `cite_or_cut` per sentence with the evidence from 4.11; strip cut sentences; keep
  `verify_numbers` as-is for `numbers_verified`.
- Canned path (no key / RED budget / tests): when a `PT-xxxx` code and a free-text question are
  present, run retrieval in BM25-only mode and return an extractive answer: the top 3 chunks as
  quoted, dated lines with `[n]`. This keeps the demo working with embeddings and LLM both off.
- UI (lane H2, `web/src/pages/Ask/`): render `result_preview` rows with `D-` refs as source chips
  (date, channel, author). Optional additive `QueryAnswer.citations: list[CitationRef]` would need an
  RFC; not required.

### 5.3 Narrator (P1, after the demo)
The nightly card stays features-only (numbers from `cm/memory`). Add at most one optional
"in their words" sentence: the narrator receives up to 3 `D-` chunks from `search_patient_memory`
with a fixed query per detected pattern (e.g. top miss weekday), may quote them, and must cite them;
`evidence_for()` gains those D ids. Cite-or-cut needs no change because `CITE` already accepts `D-`.

### 5.4 Indexing hook
- Live: after an event commits (intake, webhook handlers, `cm.review.decide`, portal routes), enqueue
  `index-event-<event_id>` via `cm.core.tasks.enqueue` (Rule 8: no work after the ack). The handler
  renders, tokenizes, dedups by `content_hash`, embeds (if enabled) and inserts; idempotent on
  `(document_id, content_hash)`.
- Nightly (`cm/memory/nightly.py`, lane C): build the closed day's `daily` rollup and, on Sundays, the
  `weekly` rollup from features; then bump `patients.data_version` (cache invalidation).
- Backfill: `python -m cm.rag.index --patient PT-0142 --rebuild` for seeded data (this is how tomorrow's
  demo patients get chunks).
- Consent withdrawal: `UPDATE text_chunks SET status='withdrawn' WHERE consent_id=$1` in the same
  transaction as the consent event (lane A, `cm/store/consent.py`), hard delete in the next sweeper run.

---

## 6. Evaluation plan: 3-day patient vs 30-day patient (tomorrow's demo)

### 6.1 Setup
- **Patient S (short):** 3 days of history. **Patient L (long):** 30 days. Both generated from the same
  sim seed and the same pattern set (recommend `market_day` + one free-text reason bank), so the only
  difference is history length. Option: use one patient and replay `as_of = day 3` vs `as_of = day 30`
  (cleanest comparison, and it also demonstrates `as_of`).
- Channels seeded for both: Telegram taps and free-text reasons (`fixtures/text_bank.json`), one Gmail
  doctor reply, web portal marks, one prescription note, one lab remark, chemist CSV refills, one doctor
  note. Same seed -> same text, deterministic.
- Index both with the same pipeline config.

### 6.2 Question set (same 12 questions for both)
1. Which day of the week does the patient usually miss doses? (pattern)
2. What reasons has the patient given for missing doses? (free text)
3. When did they last collect a refill from the chemist? (event)
4. What did the doctor say in the last email reply? (email)
5. Has the patient reported any side effects or symptoms? (free text)
6. What did the lab report remark say? (document)
7. Did the Supporter visit this week, and what did they note? (Supporter)
8. Has the patient gone quiet at any point? (rollup)
9. Did anything change in the instructions since the start? (doctor note / prescription)
10. Has self-report ever disagreed with the chemist record? (conflict; numbers from features)
11. What did the patient say on the most recent market day? (temporal + pattern)
12. Anything about the household or family members being screened? (household)

### 6.3 Gold labels (no manual labelling needed)
Because every chunk is rendered from known events, gold chunks are derived by predicates over events
and sim truth (`cm/sim/truth.py`, evaluator-only): e.g. Q1 gold = weekly rollups naming the top miss
weekday + check-in chunks with `status=missed` on that weekday; Q3 gold = the latest `Dispense` chunk
`<= as_of`. For S, several questions have **no** gold (correct behaviour = abstain).

### 6.4 Metrics

| Metric | Level | Definition | Expected direction (hypothesis, not measured) |
|---|---|---|---|
| recall@5, recall@10 | retrieval | share of gold chunks in top k | L high on pattern questions only with rollups on |
| MRR | retrieval | mean of 1/rank of first gold chunk | L > S where gold exists |
| nDCG@10 (optional) | retrieval | graded: rollup and event both gold | |
| Abstain accuracy | answer | correct "not in the record" when gold is empty | S should abstain on Q1, Q8, Q11 |
| Citation validity | answer | share of cited ids that exist, belong to the patient, are `<= as_of` and were in the retrieved set | 100% target (hard gate) |
| Citation support | answer | share of kept sentences whose cited chunk entails them (JUDGE model if set; else keyword overlap check) | >= 95% target |
| Groundedness / cut ratio | answer | `1 - cut_ratio` from `cite_or_cut` | report both patients |
| Answer correctness | answer | for Q1/Q3/Q10 compare to truth (weekday, date, conflict flag) | L correct, S abstains |
| Isolation | safety | adversarial: ask about S while scoped to L; zero foreign chunk ids | 100% |
| Temporal leakage | safety | L at `as_of=day 3` returns no chunk with `recorded_at > day 3` | 100% |
| Latency p50/p95, tokens, cost | ops | from `task_runs` usage rows | p95 retrieval < 300 ms |

Ablation rows (one table per patient): BM25-only, vector-only, hybrid RRF, hybrid + MMR,
hybrid + MMR + LLM rerank, and event-only vs event + rollups. Pick the cheapest config within 2 points
of the best recall@10 (v1 rule).

### 6.5 Demo story
Show the same question (Q1) for S and L side by side: S answers "Not in the record up to day 3" with the
3 nearest sources; L answers "Misses cluster on Tuesdays [D-..][B-weekday_pattern]" with chips that open
the weekly rollup and the two check-ins. Then the metric table (recall@10, MRR, citation validity,
groundedness) for S vs L, and the leakage test: L replayed at day 3 behaves like S.
Output: `cm/eval/rag_eval.py` writes `eval_rag_seed<seed>.json`; the Eval page (lane H2) adds one panel.

---

## 7. Risks, PII rules, cost

### 7.1 Risks

| Risk | Mitigation |
|---|---|
| Embeddings disabled in this checkout (`EMBEDDING_MODEL` empty, no OpenAI key) | Pipeline runs BM25-only by design; vector leg switches on when the key and model are set. Decide D2 |
| Rollups put numbers into embedded text (v1 invariant: "structured numbers are never embedded") | Rollup numbers are deterministic `cm/memory` outputs, cited as `B-` refs; cite-or-cut still checks every answer number against evidence. Needs owner sign-off (D4) |
| Frozen contracts | Option A (extra JSONB) needs no RFC; RFC-R1..R3 for the clean schema |
| Scope ruling (patient RAG was P1, "never start before H18") | Owner decision D1 |
| Retrieval answers drift into advice or names drugs | Same system prompt rules + `find_banned_terms` + doctor-audience only; prescription chunks never shown to patient/Supporter |
| Cross-patient leakage | token injected by the wrapper; SQL filter; isolation test is a hard gate |
| Late or corrected events | supersede via `events.supersedes`; chunk `status='superseded'` (+ `valid_to` under RFC-R3) |
| Tokenizer misses a name in free text | `register_names()` with the patient's and Supporter's names before rendering; `assert_clean()` runs before every embed call |
| Mixed embedding models in one index | `embedding_model` column; re-embed into a new column (v1 section 6) |
| Small eval set (12 x 2) overstates certainty | Report it as a demo, not a benchmark; run 3 seeds if time allows |

### 7.2 PII rules (non-negotiable, from CLAUDE.md Rules 10, 16, 17)
1. Render -> `tokenize(text, names=patient+supporter names)` -> store tokenized `content` -> embed that
   same text. Never embed raw text. `assert_clean()` in `llm.py` already guards the embed call.
2. Query text is tokenized the same way before embedding and before BM25.
3. No PII in `extra`, logs or task ids; task ids colon-free.
4. Embeddings go to OpenAI only (`OPENAI_ONLY` includes `EMBEDDING`); with `CM_DATA_CLASS=real` DeepSeek is
   refused for generation; LLM rerank must then use an OpenAI WORKER model.
5. Erasure: delete chunks by `consent_id` / `patient_token`; embeddings and `tsv` are derived data and
   are deleted too.

### 7.3 Cost (estimates, not measured)
30-day patient: about 12K tokens indexed once (event chunks without free text can skip embedding), about
$0.0003 at the v1 small-model rate (about $0.02 per 1M tokens, **UNVERIFIED** current price). Per question:
one query embedding (negligible) + one WORKER answer call (about 2-3K tokens in, 300 out), plus one more
call if LLM rerank is on. Demo total for 2 patients x 12 questions x 6 ablation configs: well under $1.
Generation dominates; retrieval is nearly free.

---

## 8. Task breakdown into parallel lanes (file ownership per CLAUDE.md lane table)

| Lane | Owner files | Tasks | Depends on | Est. h |
|---|---|---|---|---|
| L0 (Opus) | `cm/contracts/CHANGES.md`, `scripts/lanes.yaml` | Append RFC-R1..R3; register new files (`cm/tools/memory_search.py` -> N, `cm/store/chunks_repo.py` -> A, `cm/rag/*` -> K, `cm/eval/rag_eval.py` -> J); open OpenSpec change `add-patient-memory-rag` | none | 0.5 |
| A Data core | `cm/store/chunks_repo.py` (new), `cm/store/as_of.py`, `cm/store/consent.py`, later `cm/store/migrations/0009_rag_v2.sql` | insert/upsert chunk + synthetic document rows; `candidates(token, as_of, window, audience)`; `vector_topk(token, qvec, as_of, k)`; FTS fallback query; withdrawal flip | L0 | 3 |
| K RAG content | `cm/rag/render.py`, `cm/rag/chunk.py`, `cm/rag/embed.py`, `cm/rag/index.py`, `cm/rag/lexicon.py`, `cm/rag/seed.py`, `fixtures/text_bank.json` | event -> sentence templates per type; window/doc chunkers with sizes from section 2; digit guard; tokenize; dedup; embed batch via `get_model("EMBEDDING")`; backfill CLI; guideline seed | A (repo API, can stub) | 4 |
| C Memory | `cm/memory/rollups.py` (new, pure), `cm/memory/nightly.py` | daily and weekly rollup text from `PatientFeatures` with `B-` refs; nightly call into `cm.rag.index` | K interface | 2 |
| N Retrieval | `cm/tools/memory_search.py` (new), `cm/tools/guidelines.py`, `cm/agents/subagents/query.py` | BM25 leg, RRF, boosts, MMR, rerank flag, assembly, abstain threshold; `governed` wrapper; guideline search reuse | A, K | 4 |
| D Validator | `cm/validator/cite_or_cut.py` (additive function), tests | `check_sentence_local` (number must be in a chunk the sentence cites); D-ref evidence helper | none | 1 |
| G API | `cm/api/routers/query.py`, `cm/api/routers/ingest.py` | add tool to Ask loop; canned BM25 extractive path; per-sentence cite-or-cut; upload route (P1) enqueuing `index-document-<id>` | N, D | 2 |
| J Eval | `cm/eval/rag_eval.py`, `cm/eval/metrics.py` (add recall@k, MRR, nDCG), `tests/replay/` | gold builder from events + truth; question set; ablations; isolation and leakage tests; JSON output | K, N | 3 |
| B Sim/seed | `cm/jobs/seed_events.py`, `cm/sim/gen.py` | 3-day patient S and 30-day L (or replay plan) with all channels and free text | none | 1.5 |
| H2 Web | `web/src/pages/Ask/`, `web/src/pages/Eval/` | source chips for D refs; S vs L panel | G, J output shape | 2 |
| I Infra | `requirements*.txt`, `.env.example` | add `rank-bm25` (if D5 yes); names `RAG_RERANK`, `RAG_TOPK`, `RAG_MMR_LAMBDA`, `RAG_ABSTAIN_SCORE` (names only) | D5 | 0.3 |

Critical path for the demo: L0 (0.5) -> A + K + B in parallel (about 4) -> N + C (about 4) -> G + J (about 3)
-> H2 (2). About 12-14 elapsed hours with 5 agents; under 8 hours if the demo uses Option A, BM25-only
canned path, no rerank, and the eval runs as a CLI with a static JSON shown on the Eval page.

Each lane: OpenSpec tasks under the one change, `NOTES.md` in its dir, `make check` green, a fake in
`fakes.py` for new Protocols (e.g. `FakeChunkRepo`, `FakeEmbedder`).

---

## 9. Decisions and inputs needed from the owner

| # | Decision | Options | My recommendation |
|---|---|---|---|
| D1 | Pull patient-memory RAG into scope now (INTEGRATION_DECISIONS lists it as P1, "never start before H18") | yes / guideline-only / no | Yes, as a demo slice behind a flag |
| D2 | Enable embeddings: set `EMBEDDING_MODEL` and an OpenAI key in `.env` yourself (I will not read or request it) | enable / BM25-only demo | Enable if a key is available; the BM25-only path is the fallback either way |
| D3 | Schema path | Option A (JSONB, no RFC) now / RFC-R1..R3 + migration 0009 now | A now, file RFCs for after the demo |
| D4 | Accept rollup chunks that contain feature numbers (departs from v1 "numbers never embedded") | accept / event-only chunks | Accept, with `B-` refs and cite-or-cut |
| D5 | Add `rank-bm25` dependency for true BM25 | yes / use Postgres `ts_rank_cd` | Yes (pure Python, tiny) |
| D6 | Reranker | none / WORKER LLM rerank / local cross-encoder | none by default, LLM rerank as an ablation row |
| D7 | Demo patients | one patient replayed at day 3 vs day 30 / two separate patients | One patient replayed (also shows `as_of`); PT-0142 has 60 days of seeded history |
| D8 | Which sources are live vs seeded for the demo (Telegram live? Gmail live? uploads?) | per source | Seed all; show one live Telegram message being indexed if Telegram is up |
| D9 | Audience: doctor-only answers, or Supporter/patient too | doctor only / all | Doctor only for now |
| D10 | Final k, abstain threshold and the 12 questions | as in section 6.2 or edited | Approve or edit the list |
| D11 | Number of agents/lanes to run tonight and the time budget | 3-6 agents | 5 (A, K, N, J, G) + B and H2 small tasks |
| D12 | Who answers RFCs (CLAUDE.md says Opus within 30 min) | coordinator / owner | Coordinator |
