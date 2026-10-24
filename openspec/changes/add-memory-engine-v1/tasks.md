## 1. Implementation
- [x] 1.1 Belief and trust update functions + unit tests
- [ ] 1.2 Risk score + calibration test. OPEN, waiting on the owner's decision: the trained and calibrated risk
  model (`cm/memory/train_risk.py`, calibration test). Fixed documented coefficients (`risk_v1_fixed` in
  `cm/memory/risk.py`, seeded 500-draw 5th/95th interval) are accepted for the demo. Nothing is trained here.
- [x] 1.3 Conflict detection + tests: `cm/memory/conflicts.py` (`self_report_vs_refill`, `weekday_pattern_conflict`,
  pure, deterministic ids, `C:` refs); tests in `tests/unit/memory/test_pipeline_conflicts.py`
- [x] 1.4 Wire into nightly job: `cm/memory/pipeline.py` (`compute_memory` pure, `run_patient` persists through
  `cm/store/memory_repo.py`, idempotent per `as_of`), `cm/memory/nightly.py` (`run_nightly`), called from
  `cm/jobs/nightly.py` before the narrator; tests: `tests/property/test_pipeline_props.py`,
  `tests/integration/test_memory_pipeline.py` (caremem_test only)
