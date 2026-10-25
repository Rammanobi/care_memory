# ai-eval Specification

## Purpose
TBD - created by archiving change add-ai-eval-suite. Update Purpose after archive.

## Requirements

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

### Requirement: Batch-2 AI eval categories
The offline AI eval SHALL include the categories `document_extraction`, `own_data_answers` and
`question_research`, run deterministically with fake models and no database, and SHALL report per-category pass
rates and metrics (doc-type accuracy, field precision and recall, low-confidence calibration, PII, injection,
auto-writes, triage accuracy, number exactness) in `docs/design/AI_EVAL_REPORT.md`.

#### Scenario: Document extraction never writes before review
- **WHEN** any fixture document runs through the extract task
- **THEN** exactly one pending review item exists, no event or chunk is written, and the payload holds no raw PII

#### Scenario: Own-data numbers
- **WHEN** answer cards are built for a fixture record
- **THEN** every number in every card equals the hand-computed record value and every text is an approved template

#### Scenario: Question research against an adversarial model
- **WHEN** a scripted WORKER returns uncited, dosing, diagnosis, drug-name, PII and other-patient lines and an unsafe reply
- **THEN** none of them reach the brief and the suggested reply is the holding template, with the 108 line only when urgent

### Requirement: Batch-2 live mode with a 0.50 USD cap
`python -m cm.eval.ai_eval --live-batch2` SHALL run only the question-research adversarial cases on the WORKER
model (deepseek flash) through a private governor capped at no more than 0.50 USD and SHALL print cost totals only.

#### Scenario: Cap reached
- **WHEN** the governor reaches RED
- **THEN** remaining live cases are skipped with `budget_cap`
