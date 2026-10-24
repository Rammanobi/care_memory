# CareMemory: RAG research notes (evidence review for per-patient longitudinal memory)

As of 2026-10-24. Research only; no code, contract or migration changed. Companion to
`RAG_STRATEGY_v2.md` (pipeline) and `RAG_MEMORY_DESIGN.md` (v1 schema). Stack assumed: Postgres
pgvector (`halfvec(1536)`) + generated `tsvector('simple')`, OpenAI `text-embedding-3-small`,
DeepSeek flash/pro for generation, cite-or-cut, `as_of` time travel, mock data.

**Evidence tags.** `[V]` = checked this session against the source or a search of it. `[P]` = primary
source (paper/official doc) cited from prior knowledge, not re-fetched this session. `[U]` =
UNVERIFIED (my estimate, secondary source, or no source). Gains measured on public benchmarks
rarely transfer 1:1 to a ~30-170 chunk per-patient corpus; treat all numbers as priors for our eval.

---

## 0. The one fact that shapes everything: our corpus is tiny

| Patient history | Est. chunks (v2 sec 2) | Est. tokens | Source |
|---|---|---|---|
| 3 days | ~30 | ~2K | RAG_STRATEGY_v2 sec 2 estimate `[U]` |
| 30 days | ~170 | ~12K | same `[U]` |
| 60 days | ~330 | ~25K | linear extrapolation `[U]` |

Anthropic: if a knowledge base is under ~200K tokens, putting all of it in the prompt (with prompt
caching) can beat RAG `[V]` https://www.anthropic.com/news/contextual-retrieval. A 60-day patient is
~8x below that line. Consequences:
1. A **full-context baseline** (whole as_of-cut patient record, dated, with ids) must be an eval arm;
   RAG has to beat it on citation validity, cost or latency to justify itself.
2. Retrieval should favour **recall** (bigger k) over precision; the vector leg should be an **exact**
   scan of the patient's rows (no ANN, no post-filter starvation; pgvector README notes filters apply
   after the HNSW scan and `hnsw.iterative_scan` exists from 0.8.0 `[P]` https://github.com/pgvector/pgvector).
3. Long-context still degrades on facts placed mid-prompt ("Lost in the Middle") `[P]`
   https://arxiv.org/abs/2307.03172, and the record grows, so RAG remains the default beyond ~60 days.

---

## 1. Technique table

Cost/latency is per question unless noted. Effort: S < 2 h, M 2-6 h, L > 6 h in our stack.

### 1.1 Chunking

| Technique | What it is | Expected gain + evidence | Cost / latency | Effort | Medical-data risk | Verdict |
|---|---|---|---|---|---|---|
| Chunk size 128-512 tokens | Fixed token budget per chunk | No universal optimum: fact-style QA peaks at 64-128 tokens (SQuAD recall@1 64.1% at 64, falls 10-15% by 512), broad questions favour 512-1024 `[V]` https://arxiv.org/abs/2505.21700. Chroma: LangChain default 800/400 below average; ~200-400 token recursive chunks among the best `[V]` https://research.trychroma.com/evaluating-chunking | None at query time; more chunks = more embeddings (cents) | S | Big chunks mix days and blur dates/attribution | **Use now**: event/message chunks are naturally 15-120 tokens; prose 256-400; test 128 vs 256 vs 400 for prose |
| Overlap 0 / 50 / 100 / 200 | Repeat tail tokens of chunk n at head of n+1 | Chroma: overlap raised recall (60.7 vs 54.1 at 250 tok w/ 125 overlap) but cut precision/IoU `[V]` (same Chroma URL). NVIDIA: 15% best of 10/15/20% at 1,024 tok on FinanceBench, single dataset `[V]` https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/ | Index grows by overlap ratio | S | Duplicate text inflates "evidence count" for one fact; dedupe by source event ids before generation | **Use now**: 0 for atomic events and rollups; ~15% (50-60 tok) for prose >400 tok; 2-message overlap for chat windows. **Test** 0 vs 50 vs 100 on prose only; skip 200 |
| Sentence-aware / recursive | Split on paragraph -> sentence -> token boundaries | Recursive splitters at 200-400 tok match or beat fixed token splits in Chroma's table `[V]` | Free | S (`RecursiveCharacterTextSplitter`) | Telugu sentence end `.`/`।` and code-mixed text break naive splitters `[U]` | **Use now** for prose |
| Semantic chunking | Split where adjacent-sentence embedding similarity drops | Not consistently better than fixed-size; cost not justified (NAACL Findings 2025) `[V]` https://arxiv.org/abs/2410.13070. Chroma: cluster semantic 200 tok had good recall `[V]` | 1 embed per sentence at index | M | Unstable boundaries on short notes | **Skip** (our units are already semantic: one event, one message) |
| Dynamic / LLM chunking | LLM decides boundaries | Chroma: LLM chunking highest recall (~91.9) but low precision `[V]` | 1 LLM call per doc | M | LLM may rewrite or drop clinical text; PII leaves via LLM call | **Later** (only for long uploaded PDFs) |
| Structure-aware (heading/page) | Split on document structure | NVIDIA page-level chunking best average accuracy (0.648, secondary report) `[U]` (same NVIDIA URL) | Free | S | n/a | **Use now** for guidelines and long PDFs |

### 1.2 Index-time enrichment

| Technique | What it is | Expected gain + evidence | Cost / latency | Effort | Medical-data risk | Verdict |
|---|---|---|---|---|---|---|
| Parent-child (small-to-big) | Search small child chunks, send parent (section/day) to the LLM | Standard pattern in LangChain `ParentDocumentRetriever` and LlamaIndex auto-merging `[P]` https://python.langchain.com/docs/how_to/parent_document_retriever/ ; no controlled benchmark found `[U]` | Bigger prompt (+500-1,500 tok) | S (`parent_id` exists) | Parent may carry sentences the child did not; cite-or-cut must cite the child or parent id actually sent | **Use now** for doc chunks; for events the "parent" is the daily rollup |
| Contextual retrieval | Prepend a 50-100 tok LLM-written context line to each chunk before embedding and BM25 | Top-20 failure 5.7% -> 3.7% (-35%) embeddings; -49% with contextual BM25; -67% with rerank; ~$1.02 / 1M doc tokens with caching `[V]` https://www.anthropic.com/news/contextual-retrieval | 1 cheap LLM call per chunk at index | M | LLM-written context can hallucinate (wrong date/person); never put numbers in it | **Use now, deterministic variant**: template prefix `2026-02-03 Tue · Telegram · patient · week 5 · reply to dose reminder` (no LLM). **Test** LLM prefix for doc chunks only |
| Late chunking | Embed the whole document with a long-context model, then pool token vectors per chunk | Consistent BEIR nDCG gains, larger for longer docs (reported +2.7-3.6% nDCG@10, secondary) `[U]`; method `[P]` https://arxiv.org/abs/2409.04701 ; README `[V]` https://github.com/jina-ai/late-chunking | Needs token-level embeddings | L (not possible with OpenAI API, which returns one vector per input) | n/a | **Skip** (incompatible with text-embedding-3-small) |
| Hierarchical rollups (daily -> weekly -> monthly), RAPTOR-like | Store summaries at several granularities and search them alongside raw chunks | RAPTOR: +20 pts absolute on QuALITY with GPT-4; controlled retriever gain much smaller (SBERT 54.9 -> 56.6) `[V]` https://arxiv.org/abs/2401.18059. LongMemEval: storing at round granularity beats session; compressing into facts alone loses info `[V]` https://arxiv.org/abs/2410.10813 | Nightly build; deterministic = free | M | Summaries can state things the events do not; must be deterministic from `cm/memory` and keep `B-` refs | **Use now** daily + weekly (deterministic, not LLM); **later** monthly when histories > 60 days; keep raw events searchable always |
| Fact / key expansion | Index extracted facts or keyphrases as extra keys pointing to the same chunk | LongMemEval fact-augmented key expansion: recall +9.4%, QA +5.4% (secondary) `[U]` https://arxiv.org/abs/2410.10813 | 1 LLM call per chunk | M | Extracted facts may be wrong; keys only, never answer text | **Test** later (after baseline) |
| Embedding dims 512 vs 1536 | `dimensions` param truncates text-embedding-3 vectors | MTEB small 62.3 vs large 64.6 `[P]` https://platform.openai.com/docs/guides/embeddings ; recall at 512 on our data unknown `[U]` | Smaller index; irrelevant at our scale | S | none | **Later** (no benefit at ~300 rows/patient) |

### 1.3 Query-time

| Technique | What it is | Expected gain + evidence | Cost / latency | Effort | Medical-data risk | Verdict |
|---|---|---|---|---|---|---|
| Time-phrase parsing -> window filter | Turn "last week", "since Monday", "day 12" into an `occurred_at` range | LongMemEval time-aware query expansion: recall +11.3% (rounds) / +6.8% (sessions), needs a strong LLM `[V]` https://arxiv.org/abs/2410.10813 | Regex: 0; LLM: +1 call | S (regex) / M (LLM) | Wrong window silently drops evidence; widen on empty result | **Use now** (deterministic regex, relative to `as_of`); LLM parse as fallback **test** |
| Query rewriting / multi-query | LLM rewrites question or emits N variants, results fused | Rewrite-Retrieve-Read improved open-domain QA `[P]` https://arxiv.org/abs/2305.14283 | +1 LLM call (~300-800 ms) `[U]` | S | Rewrite can inject assumptions ("missed due to side effects") | **Test** (multi-query of 3, RRF-fused); default off |
| HyDE | Embed an LLM-written hypothetical answer instead of the question | Strong zero-shot dense gains when no relevance labels exist `[P]` https://arxiv.org/abs/2212.10496 | +1 LLM call | S | The hypothetical answer is invented clinical text; must never reach the user or the evidence set | **Test** low priority; skip if hybrid already ~0.9 recall@10 |
| Hybrid BM25 + vector with RRF | Run lexical and dense legs, fuse ranks by `sum w/(k+rank)` | RRF beats individual rankers and Condorcet fusion `[P]` https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf ; Anthropic: adding contextual BM25 to embeddings took failure -35% -> -49% `[V]`. Telugu MIRACL nDCG@10: BM25 0.383, mDPR 0.356, hybrid 0.602 (model-card figures) `[U]` https://huggingface.co/prithivida/miniDense_telugu_v1 | ~0 ms extra at our scale | S | Postgres `ts_rank_cd` is not BM25 (no corpus stats) `[P]` https://www.postgresql.org/docs/16/textsearch-controls.html | **Use now**: k=60, w_vec=w_lex=1.0; **test** w_lex 0.5/1/2 |
| Re-ranking: LLM listwise | Ask an LLM to reorder top-20 candidates | Reranking added the last step from -49% to -67% failure (Cohere rerank in that study) `[V]` Anthropic URL | +1 call, ~1-3 s `[U]` | S | Sends 20 chunks to an extra model call; with `CM_DATA_CLASS=real` must be OpenAI | **Test** on 30-day only |
| Re-ranking: cross-encoder | Local model scores (query, chunk) pairs | Same evidence class; `bge-reranker-v2-m3` is multilingual `[U]` latency on Cloud Run CPU | ~2 GB image, CPU latency unknown `[U]` | M | None (local) | **Later** |
| Late interaction (ColBERT) | Token-level multi-vector matching | Strong retrieval quality, high storage `[P]` https://arxiv.org/abs/2004.12832 ; Indic-ColBERT mixed vs BM25 on Telugu `[V]` https://arxiv.org/abs/2312.09508 | New index type, no pgvector native support `[U]` | L | n/a | **Skip** |
| MMR | Greedy pick maximising relevance minus similarity to already-picked items | Classic diversity re-ranking `[P]` https://www.cs.cmu.edu/~jgc/publication/The_Use_MMR_Diversity_Based_LTMIR_1998.pdf | ~0 ms | S | Can drop a second, confirming source for the same fact (medical "two sources agree" signal) | **Use now** lambda 0.7 on 30-day; per-day cap 3; **off** for 3-day |
| Time-decay / recency weighting | Multiply score by f(age) | Generative Agents: retrieval = recency (exp. decay 0.995/hour) + importance + relevance `[P]` https://arxiv.org/abs/2304.03442 ; simple recency prior wins "latest" questions but is parameter-sensitive `[V]` https://arxiv.org/abs/2509.19376 ; naive recency can hurt, best decay is domain-specific `[U]` https://arxiv.org/abs/2607.20560 | 0 | S | Old but critical facts (allergy-like notes, instruction changes) get buried | **Use now, gentle and intent-gated**: boost only when the question asks "latest/last/recent"; otherwise ≤10% boost. Never filter out by age |
| Metadata pre-filters | SQL WHERE on patient, as_of, status, consent, sensitivity, window | Required for isolation and correctness, not for recall; pgvector post-filter caveat `[P]` pgvector README | ~0 | S | Missing a filter = cross-patient or future-data leak | **Use now** (hard gate in eval) |
| Context ordering | Order final chunks by date; put best evidence at start or end | Mid-context facts are used worst `[P]` https://arxiv.org/abs/2307.03172 | 0 | S | n/a | **Use now**: date-ascending timeline, plus the top-2 by score repeated in a short "key evidence" header `[U]` |
| Top-k for generation | How many chunks reach the LLM | Anthropic: 20 beat 10 and 5 `[V]` | More input tokens (cheap on DeepSeek) | S | More noise -> more cut sentences | **Use now**: 3-day = all chunks; 30-day k=12-20; **test** 8/12/20 |

### 1.4 Long-term memory systems (what to borrow)

| System | Idea | Evidence | Borrow? |
|---|---|---|---|
| MemGPT / Letta | OS-style tiers: in-context core memory + archival/recall stores paged by the agent `[P]` https://arxiv.org/abs/2310.08560 | Qualitative + DMR tasks | Borrow the tiering idea only: memory card (core) + chunks (archival). **Skip** agent-driven self-editing (not auditable) |
| Mem0 | LLM extracts and updates salient facts (add/update/delete/no-op) | +26% relative over OpenAI memory on LoCoMo, 91% lower p95 latency, >90% fewer tokens vs full context `[V]` abstract https://arxiv.org/abs/2504.19413 | **Later**: extracted facts as extra keys only; LLM "delete" conflicts with append-only events |
| Zep / Graphiti | Bitemporal knowledge graph (valid time + ingestion time) | Up to +18.5% accuracy, -90% latency vs full context on LongMemEval (secondary summary) `[U]` https://arxiv.org/abs/2501.13956 | **Borrow** bitemporality (already: `occurred_at` + `recorded_at` + RFC-R3 `valid_to`). **Skip** graph store |
| LangMem | LangGraph-native semantic/episodic/procedural memory with background consolidation `[P]` https://langchain-ai.github.io/langmem/ | No benchmark found `[U]` | **Later** for doctor preference memory, not patient evidence |
| LongMemEval | Benchmark of 5 memory abilities incl. temporal reasoning and knowledge updates `[V]` https://arxiv.org/abs/2410.10813 | Round-level storage + time-aware expansion help | **Use now** as eval design template (temporal, update, abstain question types) |

**Consolidation / forgetting for medical records.** Never forget evidence: events are append-only and
legally relevant. "Forgetting" = (a) ranking demotion via superseded status and gentle decay,
(b) summarising old weeks into rollups that are *searched first* while raw events stay searchable,
(c) consent-withdrawal hard deletes. Mem0-style LLM delete/update is **skip** for evidence `[U]`.

---

## 2. Short (3-day) vs long (30-60 day) histories: how retrieval should adapt

| Setting | 3-day (~30 chunks, ~2K tok) | 30-day (~170, ~12K) | 60-day (~330, ~25K) | Why |
|---|---|---|---|---|
| Strategy | Send all live chunks (no ranking needed) | Hybrid + RRF, k=12-20 | Hybrid + RRF + rollups first, k=20 | Corpus below any rerank payoff; Anthropic small-KB note `[V]` |
| Rerank | Off | Test LLM rerank | Test | Pool too small to reorder usefully `[U]` |
| MMR | Off | On, lambda 0.7 | On, lambda 0.6 + per-day cap | Redundancy grows with history `[U]` |
| Rollups | Daily only | Daily + weekly | + monthly | Pattern questions need aggregated units (RAPTOR/LongMemEval) |
| Recency | Off | Intent-gated | Intent-gated | Avoid burying early instructions |
| Abstain | Expected often (patterns need >= 7 days) | Threshold on fused score | same | Gold-empty questions on S |

Rule of thumb for the harness: `if n_live_chunks <= 60: k = n_live_chunks, no rerank, no MMR` `[U]`.

---

## 3. Telugu and code-mixed retrieval caveats

| Issue | Detail | Mitigation |
|---|---|---|
| No Postgres Telugu stemmer | `simple` config only lowercases/splits; no stemming for Telugu agglutination `[P]` PG docs above | Keep `simple`; add a small lexicon (EN <-> Telugu <-> transliterated) for the lexical leg (v2 `cm/rag/lexicon.py`) |
| Script mixing | Same word in Telugu script, Latin transliteration ("mandu" = medicine) and English | Normalise: store both original and a transliterated copy in `tsv` input `[U]` |
| Dense quality | text-embedding-3-small MIRACL avg 44.0 vs ada-002 31.4; no Telugu-specific figure published `[V]` https://www.pinecone.io/learn/openai-embeddings-v3/ | Measure: Telugu paraphrase subset in the eval set |
| Hybrid helps most | Telugu MIRACL: hybrid well above either leg (0.602 vs 0.383/0.356, model card) `[U]` | Keep both legs on for Telugu |
| Tokens per word | Telugu script costs several times more tokens than English `[U]` | Size chunks in tokens, not characters |
| PII tokenizer | Name regexes tuned for English may miss Telugu names `[U]` | `register_names()` with script variants before rendering |

---

## 4. Evaluation methods

| Metric | Use | Pitfall |
|---|---|---|
| recall@k (k=5,10,20) | Main retrieval metric; gold from event predicates + sim truth (v2 6.3) | With tiny corpora recall@20 saturates; also report recall@5 |
| MRR | Rank of first gold chunk | Ignores other gold items |
| nDCG@10 | Graded gold (rollup = 2, raw event = 1) | Grade choice drives result; fix grades before running |
| Abstain accuracy | Gold-empty questions (3-day patterns) | Over-abstention looks safe; report false-abstain too |
| Citation validity | Cited id exists, same patient, `<= as_of`, was retrieved | Hard gate 100%; deterministic, no LLM |
| Citation support / groundedness | Kept sentence entailed by cited chunk; `1 - cut_ratio` | RAGAS-style metrics are LLM-based `[P]` https://arxiv.org/abs/2309.15217 |
| Answer correctness | Weekday/date/flag vs sim truth | Only for questions with structured truth |
| Leakage / isolation | Day-3 replay sees no day-4 rows; no foreign patient ids | Hard gate |

**LLM-judge pitfalls** (MT-Bench study: position bias, verbosity bias, self-enhancement bias `[P]`
https://arxiv.org/abs/2306.05685): use a judge from a different family than the generator (OpenAI
JUDGE vs DeepSeek generator), randomise order in pairwise tests, use binary "supported / not
supported" per sentence instead of 1-10 scores, hand-check 20 samples, report judge-human agreement.
**Small-n caveat:** 12 questions x 2 replays cannot separate configs differing by < ~10 pts recall;
run 3 sim seeds and paraphrase each question 3x (EN, Telugu, code-mixed) -> 108 queries per replay `[U]`.

---

## 5. Failure modes to test explicitly

| Failure | Example | Detection | Guard |
|---|---|---|---|
| Temporal leak | Day-3 replay cites a day-5 rollup | Leakage test | `recorded_at <= as_of` + RFC-R3 `valid_to` |
| Stale rollup | Late event changes day 12 but rollup unchanged | Compare rollup ids vs events | Rebuild at window close; valid_to |
| Wrong attribution | Supporter's words cited as patient's | Check `author_role` in cited chunk | Role in deterministic prefix |
| Negation lost | "did NOT have fever" retrieved for "fever?" and answered as yes | Support judge | Keep full sentence; judge per sentence |
| Duplicate evidence | Overlap windows count one message twice | Dedupe by `source_event_ids` | Dedupe before generation |
| Summary hallucination | Rollup says "missed 3" when 2 | Rollup numbers vs `cm/memory` | Deterministic rollups only |
| Lost in the middle | Key chunk ignored at position 9/20 | Position ablation | Key-evidence header, date order |
| Over-abstain / under-abstain | 30-day says "not in record" for a present fact | Abstain accuracy both ways | Threshold tuned on eval |
| Script mismatch | Telugu question, English chunk, BM25 zero hits | Per-language recall | Lexicon + dense leg |
| Generic "similar" match | "missed dose" query returns every missed tap, no reasons | recall on reason chunks | Weekly rollups, MMR |
| Cross-patient leak | Name in question resolves wrong patient | Isolation test | Token injected server-side |

---

## 6. Ranked experiment plan (eval harness, one patient replayed at as_of day 3 vs day 30)

Owner rulings (2026-10-24): (1) no re-ranking for the hackathon: rerank stays in code, off by default,
excluded from the grid unless `--with-rerank`; (2) the headline demo is **PT-0142 replayed at as_of
day 3, day 30 (and day 60 for reference)**, same questions, same patient, only visible memory differs.
Headline table columns (to live in `RAG_EVAL_PLAN.md`): day, #events visible, #chunks, recall@5, MRR,
abstain accuracy, citation validity, one example answer per day.

Each row is one ablation against the baseline (= recommended default below). Primary metric is
recall@10 (retrieval) unless stated; always also log citation validity (must stay 100%), abstain
accuracy, cut ratio, p95 latency, tokens.

| # | Variable | Values | Metric | Expected winner (hypothesis) `[U]` |
|---|---|---|---|---|
| 1 | Retrieval mode | full-context (all as_of chunks) / hybrid RRF k=12 / hybrid k=20 | answer correctness, citation support, tokens | 3-day: full-context = hybrid (tie, choose full); 30-day: hybrid k=20 matches full-context at ~1/3 tokens |
| 2 | Legs | BM25-only / vector-only / hybrid RRF | recall@10, MRR, per language | Hybrid, largest gap on Telugu and code-mixed queries |
| 3 | Rollups | events only / + daily / + daily + weekly | recall@10 on pattern questions (Q1, Q8, Q11) | + daily + weekly on 30-day; no difference on 3-day |
| 4 | Contextual prefix | none / deterministic template / LLM (docs only) | recall@10, MRR | Template captures most of the gain at zero cost |
| 5 | Final k to LLM | 8 / 12 / 20 | answer correctness, cut ratio | 3-day: all; 30-day: 12-20 |
| 6 | Multi-query rewrite (owner ruling: rerank is out of the grid; only with `--with-rerank`) | off / 3 variants RRF-fused | recall@10, latency | off on 3-day; small gain on 30-day paraphrase/Telugu queries, likely not worth +1 call |
| 7 | RRF lexical weight | w_lex 0.5 / 1.0 / 2.0 | recall@10 | 1.0 overall; 2.0 on name/term-heavy questions |
| 8 | Recency | off / always 0.1 boost / intent-gated | MRR on "latest" questions + recall on old-fact questions | Intent-gated |
| 9 | MMR | off / lambda 0.7 / 0.5 | distinct-day coverage, recall@10 | 30-day: 0.7; 3-day: off |
| 10 | Prose chunk size / overlap | 128/0, 256/0, 256/40, 400/60 | recall@10 on doc questions | 256-400 with ~15% overlap (few prose docs, small effect) |

Selection rule (from v1): pick the cheapest config within 2 points of the best recall@10 that keeps
citation validity 100% and leakage 0.

---

## 7. Recommended default configuration

| Knob | Default | Source / reason |
|---|---|---|
| Chunk units | 1 event = 1 chunk; chat window 6 msgs, 2 overlap, cap 256 tok; prose recursive 400 tok / 60 overlap; guidelines heading-aware 400/50 | Sec 1.1; Chroma, NVIDIA, 2505.21700 |
| Rollups | Deterministic daily + weekly (no LLM), searched together with raw events | RAPTOR, LongMemEval |
| Contextual prefix | Deterministic template (date, weekday, channel, author role, week n), embedded and indexed | Anthropic contextual retrieval, no-LLM variant |
| Embedding | text-embedding-3-small, 1536 d, exact scan per patient | pgvector post-filter caveat |
| Lexical | BM25 in Python over prefiltered pool (`ts_rank_cd` fallback), `simple` tsv + EN/Telugu lexicon | PG docs |
| Fusion | RRF k=60, w_vec=w_lex=1.0 | Cormack 2009 |
| Pre-filters | patient token (server-injected), `as_of` on `occurred_at` and `recorded_at`, status, consent, sensitivity, optional parsed time window | Isolation, time travel |
| Small-corpus switch | `n_live <= 60`: send all chunks, no MMR, no rerank | Anthropic small-KB note |
| k to LLM | 12 (test 20) | Anthropic top-20 finding |
| MMR | lambda 0.7, max 3 chunks/day, dedupe by `source_event_ids` | Carbonell & Goldstein |
| Recency | Only when the question asks for latest/last/recent: `1 + 0.1*exp(-age_days/14)` | Generative Agents, 2509.19376 |
| Rerank | Off; not in the experiment grid (owner ruling), only via `--with-rerank` | Small pool |
| Query rewrite / HyDE | Off; regex time parsing on | Cost vs uncertain gain |
| Context order | Date ascending + top-2 "key evidence" header | Lost in the Middle |
| Generation | DeepSeek flash, temperature 0, JSON sentences, cite-or-cut, abstain on low score | Existing narrator pattern |
| Eval | recall@5/10, MRR, nDCG@10, abstain, citation validity (gate), support (cross-family judge), leakage (gate) | Sec 4 |
