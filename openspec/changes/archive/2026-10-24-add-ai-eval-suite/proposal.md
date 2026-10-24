## Why
Before the public push the owner needs a repeatable, high-signal eval of every AI-facing part: cite-or-cut, the
narrator, the Ask box, the doctor gate and the rule/LLM boundary, plus the Day 3 / 30 / 60 risk metrics. The
existing tests cover happy paths; nothing measured adversarial behaviour (fabricated refs, injections, PII
exfil, advice requests, Telugu input) or ran the same cases against the real model.

## What Changes
- New `cm/eval/ai_eval.py` + runner `python -m cm.eval.ai_eval [--live] [--max-usd] [--only] [--rescore-live]`.
- Golden dataset `fixtures/ai_evals/{cite_or_cut,narrator,ask_box,gate}.json` (mock data, English + Telugu).
- Six categories: cite_or_cut, narrator (groundedness, invented numbers, banned terms, advice/diagnosis, tone),
  ask_box (intent routing, advice refusal, prompt injection incl. hidden note instructions, PII exfil,
  unanswerable -> not in the record), doctor_gate (outbox writer allow-list, interrupt before approval,
  patient-facing banned-term blocks), boundary (no LLM imports in memory/rules/risk eval; stored numbers and
  tier come from features), longitudinal (Brier/ECE/AUROC at Day 3, 30, 60 over 10 seeds).
- Offline mode (default, CI): scripted fake models routed through the real GovernedModel (PII guard, budget),
  no network. Live mode: WORKER = deepseek flash for subject and JUDGE (LLM-as-judge with a rubric), private
  in-memory governor with a hard cap (<= 1.00 USD per run), prints cost totals only.
- Reports: `out/evals/ai_eval_<mode>.{json,md}` (git-ignored) and summary `docs/design/AI_EVAL_REPORT.md`.
- `tests/evals/test_ai_evals.py`: one pytest case per golden case; `known_gap` cases are xfail(strict).

Out of scope: fixing the open gaps found (listed in the report; they belong to lanes D/E/G/N/C); `web/`,
`cm/rules`, `cm/memory`, `cm/channels` untouched. The cite parser fix is its own change `fix-cite-parser`.
Lane: J (eval). `fixtures/ai_evals/` is a new fixture folder (owner-requested location). No `cm/contracts/` change.
Spec section: EVALUATION_PLAN / RAG_STRATEGY_v2 section 6 (answer-level eval).
