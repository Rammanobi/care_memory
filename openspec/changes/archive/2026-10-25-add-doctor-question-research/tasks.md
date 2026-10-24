## 1. Triage

- [x] 1.1 `cm/agents/question_research.py`: `Triage`, `triage()` with EN/TE/HI keyword lexicons; danger via `cm/channels/tg_text.py` + Hindi. Test: `tests/unit/agents/test_question_research.py::test_triage_*`

## 2. Research

- [x] 2.1 `cm/store/question_repo.py`: read-only `patient_context(token)` (patient id, vault lang). Test: integration `test_vault_language_*`
- [x] 2.2 Context gathering: `search_memory` + `compute_features`, deterministic fact lines. Test: integration day-3 vs 60-day
- [x] 2.3 WORKER brief: tokenised prompt, temperature 0, JSON, cite-or-cut + content guard + doctor banned lexicon. Test: `test_cut_*`, `test_injection_*`
- [x] 2.4 Deterministic gap line, little-history line, clinical-judgment line, confidence. Test: `test_day3_*`
- [x] 2.5 Suggested reply validator + EN/TE holding template + urgent 108 line. Test: `test_reply_*`, 40-question banned-term sweep
- [x] 2.6 Offline/RED degrade to extractive brief; failure returns status failed. Test: `test_offline_*`, `test_failure_*`

## 3. Fixtures and live

- [x] 3.1 `fixtures/ai_evals/question_research.json` (40+ questions EN/TE/HI, adversarial)
- [x] 3.2 `tests/integration/test_question_research.py` on caremem_test demo patients (3/30/60 days) + `@pytest.mark.live` deepseek flash run capped at $0.10
