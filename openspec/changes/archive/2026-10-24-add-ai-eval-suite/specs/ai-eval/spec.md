## ADDED Requirements

### Requirement: Offline AI eval suite
The system SHALL provide `python -m cm.eval.ai_eval` that runs golden AI eval cases from `fixtures/ai_evals/`
offline with scripted models routed through the real governor and PII guard, with no network access, and SHALL
write JSON and Markdown reports to `out/evals/` and a summary to `docs/design/AI_EVAL_REPORT.md`.

#### Scenario: CI run
- **WHEN** `pytest tests/evals` runs without keys or network
- **THEN** every golden case runs, known gaps are xfail(strict) and any other failure fails the build

### Requirement: Live AI eval with a hard cost cap
The live mode SHALL use only the WORKER model (deepseek flash) for the subject and the JUDGE role, through a
private budget governor capped at no more than 1.00 USD per run, SHALL skip remaining cases once the governor is
RED, and SHALL print only cost and token totals, never keys or environment values.

#### Scenario: Cap reached
- **WHEN** the governor-estimated spend passes 90% of the cap
- **THEN** remaining live cases are reported as skipped (`budget_cap`) and no further provider call is made

#### Scenario: Non-flash worker
- **WHEN** `WORKER_MODEL` is not a deepseek flash model
- **THEN** the live mode refuses to start

### Requirement: Eval coverage
The golden set SHALL cover cite-or-cut, narrator groundedness and safety, Ask-box routing and adversarial
inputs (advice, prompt injection, PII exfil, unanswerable), the doctor gate, the rule/LLM boundary and Day 3 /
30 / 60 risk metrics, in English and Telugu.

#### Scenario: Coverage floor
- **WHEN** the suite is collected
- **THEN** all six categories and both languages are present and the Ask box has advice, injection, pii and unanswerable cases
