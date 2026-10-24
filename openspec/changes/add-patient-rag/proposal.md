## Why
Patient history (taps, notes, refills, visits, doctor decisions) can only be searched by exact fields. Patient-level
free-text questions ("why did she miss Tuesdays?") need a rebuildable, per-patient, as_of-safe text index over the
event log. RAG_STRATEGY_v2.md sections 2-3 (Option A, no schema change) define it.

## What Changes
Several lanes append tasks to this one change. Lane A+K (render, chunk, index) adds:
- `cm/rag/render.py`: deterministic, name-free, number-free sentence per event type (lab values and CSV rows never rendered).
- `cm/rag/chunk.py`: `chunk_text(text, size_tokens, overlap_tokens, strategy)` with `fixed`, `sentence`, `event`, `dynamic`
  (tiktoken cl100k, word fallback), plus parent linking for windows.
- Rollup chunks (daily, weekly) built only from `cm.memory.features`; numbers allowed on these cards only and mirrored in `extra`.
- `cm/rag/index.py`: idempotent `build_patient_index(...)` through `cm/store/chunks_repo.py` (the only SQL), with an
  injected `Embedder` Protocol; text is tokenized and `assert_clean` before storage; only events visible at `as_of`.
- `cm/store/chunks_repo.py`: documents and text_chunks upserts and reads.

## Out of scope
Embedding provider (`cm/rag/embed.py`), retrieval, rerank, `memory_search` tool, RAG eval (other lanes). No contract or
migration change (Option A: `extra.chunk_kind`, `extra.source_event_ids`, `extra.window`).

## Owning lane
A (store) + K (rag). Implements RAG_STRATEGY_v2.md sections 2-3. No change to `cm/contracts/`.
