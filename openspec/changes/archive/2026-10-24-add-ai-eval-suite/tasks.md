## 1. Dataset
- [x] 1.1 `fixtures/ai_evals/cite_or_cut.json` (26 cases, EN+TE) - tests/evals
- [x] 1.2 `fixtures/ai_evals/narrator.json` (3 mock patients, 18 cases) - tests/evals
- [x] 1.3 `fixtures/ai_evals/ask_box.json` (13 routing, 11 safety) - tests/evals
- [x] 1.4 `fixtures/ai_evals/gate.json` (12 patient-facing strings EN/TE/HI) - tests/evals

## 2. Harness
- [x] 2.1 `cm/eval/ai_eval.py`: categories, governed fakes, text detectors, Day 3/30/60 metrics
- [x] 2.2 Live mode: flash-only env, capped governor, judge rubrics, `--only`, `--rescore-live`
- [x] 2.3 Reports to `out/evals/` and `docs/design/AI_EVAL_REPORT.md`

## 3. Tests and runs
- [x] 3.1 `tests/evals/test_ai_evals.py` (per-case, coverage floor, detectors, report, live wiring) green
- [x] 3.2 Offline run: 0 unexpected failures
- [x] 3.3 Live run on deepseek flash within cap; results in the report
