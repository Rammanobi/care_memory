## 1. Eval batch 2
- [x] 1.1 `fixtures/ai_evals/doc_extraction.json` (39 docs, 4 flows), `own_data.json` (26), question_research `adversarial_batch2` (11)
- [x] 1.2 `cm/eval/ai_eval_batch2.py`: document_extraction, own_data_answers, question_research cases, metrics, `--live-batch2`
- [x] 1.3 Wire into `cm/eval/ai_eval.py` (CATEGORIES, offline_cases, KNOWN_GAPS DOC-IMG-TYPE, metrics in the report)
- [x] 1.4 `tests/evals/test_ai_evals.py`: batch-2 coverage floor, metrics and live-cap wiring (`pytest tests/evals`)

## 2. Bug fixes found by the eval
- [x] 2.1 `cm/uploads/extract.py` whole-word, Telugu, bill-needs-medicine doc-type guess (doc-* cases; tests/unit/uploads/test_extract_review.py)
- [x] 2.2 `cm/uploads/review.py` mask the filename in the review payload (doc-pii-filename)
- [x] 2.3 `cm/api/own_data.py` `safe_when` + `cm/api/routers/portal.py` (od-visit-free-text-*; tests/unit/api/test_own_data.py)
- [x] 2.4 `cm/agents/question_research.py` Hindi danger variants (adv2-hi-danger-yellow-eyes; tests/unit/agents/test_question_research.py)

## 3. Report
- [x] 3.1 Offline run and live batch-2 run (0.018 USD of the 0.50 cap); `docs/design/AI_EVAL_REPORT.md` regenerated
