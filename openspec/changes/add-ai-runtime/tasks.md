## 1. Implementation
- [x] 1.1 `cm/memory/features.py` + tests/unit/ai/test_features.py
- [x] 1.2 `cm/validator/cite_or_cut.py` + tests/unit/ai/test_cite_or_cut.py (covered in test_narrator.py)
- [x] 1.3 `cm/tools/ai_tools.py`, `cm/store/ai_repo.py` + tests/unit/ai/test_tools.py (done via cm/tools/readonly.py + tests/unit/ai/test_governor.py; no ai_tools.py/test_tools.py)
- [x] 1.4 `cm/agents/narrator.py` + tests/unit/ai/test_narrator.py
- [x] 1.5 `cm/agents/orchestrator.py` + tests/unit/ai/test_orchestrator.py, tests/integration/test_ai_orchestrator.py (unit done; integration covered by tests/integration/test_ai_nightly.py)
- [x] 1.6 `cm/jobs/nightly.py`, `cm/jobs/ai_smoke.py`
- [x] 1.7 `cm/api/routers/query.py` + tests/unit/ai/test_query_llm.py (tests/integration/test_ai_query.py)
- [ ] 1.8 One live run for PT-0142; record numbers in cm/agents/NOTES.md (NOT DONE: cm/agents/NOTES.md missing, no live run recorded)
