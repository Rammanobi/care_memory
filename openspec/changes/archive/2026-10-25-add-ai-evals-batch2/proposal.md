## Why
The AI eval suite (`add-ai-eval-suite`) did not cover three AI-facing parts the owner demos: document upload
extraction (doctor review drafts), the patient's own-record answer cards, and the question-research doctor brief.
Each needs an offline, deterministic regression set with adversarial inputs (prompt injection, PII, other
patients' codes, dosing requests, Telugu/Hindi danger words, OCR noise, empty and non-medical files).

## What Changes
- New `cm/eval/ai_eval_batch2.py`, wired into `python -m cm.eval.ai_eval` (categories `document_extraction`,
  `own_data_answers`, `question_research`) and `tests/evals/test_ai_evals.py` (one pytest case per golden case;
  known gaps xfail strict). Per-category metrics are added to the report.
- Fixtures: `fixtures/ai_evals/doc_extraction.json` (39 synthetic documents + 4 review flows),
  `fixtures/ai_evals/own_data.json` (26 patient records), `fixtures/ai_evals/question_research.json` gains
  `adversarial_batch2` (11 questions; the 45-question `questions` list is unchanged).
- Document pipeline runs `run_document_extract` / `on_approved` / `on_decided` with all store seams patched in
  memory (no DB) and a fake vision model: doc_type accuracy, field precision/recall, low-confidence calibration,
  abstain cases, PII never in the review payload, injection ignored, patient-facing text clean, zero writes
  before approval.
- Own-data: every number equals the hand-computed record value, templates only, banned-term/PII/advice clean,
  history card under 3 check-ins, advice footer last, future events invisible, deterministic.
- Question research: triage, every brief line cited, no dosing/diagnosis/drug names, PII and other-patient
  codes absent, holding-style reply, 108 line iff urgent; each question offline and against an adversarial fake.
- `--live-batch2`: question-research adversarial set on the WORKER model (deepseek flash), private governor
  hard-capped at 0.50 USD, cost totals only.
- `docs/design/AI_EVAL_REPORT.md` regenerated.

Product bugs found and fixed (minimal edits):
1. `cm/uploads/extract.py`: the doc-type guess matched substrings ("lab" in available/label, "report" in
   reported, "result", "mg" in among) and called any bill a chemist bill; Telugu documents were always `other`.
   Now whole words, a bill needs a medicine cue, Telugu cue words added. Doc-type accuracy 0.77 -> 0.97.
2. `cm/uploads/review.py`: the upload filename reached the doctor review payload unmasked (phone number in a
   filename). Now PII-tokenised like the text.
3. `cm/api/own_data.py` (+ the today card in `cm/api/routers/portal.py`): the `{when}` slot of an approved
   template carried any banned-term-clean free text (advice, phone numbers) to the patient. New `safe_when`: a
   short date/time phrase only, else withheld.
4. `cm/agents/question_research.py`: Hindi danger words missed the chandrabindu spelling of "yellow eyes" and
   vomiting (a danger word in the English and Telugu lexicons), so such questions were `high`, not `urgent`.

Open gap (xfail): DOC-IMG-TYPE, an unnamed photo (IMG_2041.jpg) is read with the prescription prompt and the
vision model's own doc_type is overwritten.

Out of scope: live document extraction (VISION is not a deepseek model); the existing banned-term hit in
`web/src/pages/PatientApp/patientMock.test.ts` (another lane). No `cm/contracts/` change.

Lane: J (eval), with minimal cross-lane bug fixes in G (own_data, portal), uploads, and question research.
Spec section: EVALUATION_PLAN (answer-level eval), document upload, patient own answers, question routing.
