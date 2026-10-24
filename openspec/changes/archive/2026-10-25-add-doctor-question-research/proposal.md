## Why

Patients ask clinical questions in free text (Telegram or the patient app): "can I eat this food?", "can I
take this tablet?", symptoms, visit changes. The system must never answer those itself (non-negotiables 4
and 5). Today the doctor only sees the raw question. The doctor needs a short, cited summary of what the
record shows that is relevant to the question, plus a safe reply they can edit and approve.

## What Changes

- New module `cm/agents/question_research.py` (lane: question-research agent, coordinated by Opus):
  - `triage(text) -> Triage`: deterministic category (`medicine|food|symptom|visit|admin|other`), priority
    (`normal|high|urgent`), `needs_doctor`, matched keywords. English, Telugu and Hindi keywords; danger
    words reuse the Telegram danger lexicon (`cm/channels/tg_text.py`) and add Hindi danger words.
  - `research_question(patient_token, question, *, as_of=None, model=None, embed=True) -> ResearchResult`:
    patient context from `cm.tools.memory_search.search_memory` (hybrid RAG, as_of safe, token bound
    server-side) and `cm.memory.features` (adherence, refills, quiet days, conflicts); the WORKER model
    (governed, PII tokenised, temperature 0, JSON) writes a doctor-facing brief; every sentence passes
    cite-or-cut, the content guard and the doctor-audience banned lexicon or is dropped; deterministic
    lines add "what the record does NOT show", a little-history warning and a fixed clinical-judgment line.
  - Suggested patient reply: the model may propose it; a deterministic validator (patient banned lexicon,
    content guard, no advice verbs, no numbers except the 108 line, 1-3 sentences, language, must defer to
    the doctor) decides; any failure falls back to a fixed holding reply (EN/TE, urgent adds the 108 line
    from `telegram_ack_urgent_v1`). The holding reply does not tell the patient to stop or continue
    anything because no approved template says so.
  - Offline: a scripted fake model is used as given; no key or RED budget gives an extractive brief
    (BM25 chunks + feature facts). Failures never raise: `status='failed'` with a reason.
- New read-only store helper `cm/store/question_repo.py` (`patient_context`: patient id + vault language)
  because no existing repo returns the vault language without a Telegram binding (non-negotiable 6: SQL
  only in `cm/store`).
- Tests: `tests/unit/agents/test_question_research.py`, `tests/integration/test_question_research.py`
  (caremem_test only), eval fixture `fixtures/ai_evals/question_research.json`.

**Out of scope:** wiring into the Telegram handler, task queue, portal routers, approvals, web UI and the
doctor email notifier (other agents). No contract edits (`cm/contracts/` untouched). No outbound send.

Owning lane: question-research agent (new files only). Spec section: CLAUDE.md non-negotiables 3, 4, 5,
10, 11, 16; RAG_STRATEGY_v2 5.1; docs/design/RAG_RESEARCH_NOTES.md section 7.
