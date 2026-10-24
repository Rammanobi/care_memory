## Why

The router (lane F) needs approved message templates in English and Telugu, a fixture bank for tests and the simulator, and a banned-term scanner that enforces the rule that no patient or Supporter text says TB, tuberculosis or a drug name (CLAUDE.md non-negotiable 5).

## What Changes

- Add 12 approved templates in `cm/router/templates/*.yaml` (routine reminders, confirmations, Supporter weekly summary, emergency note). Each has id, kind, audience, tier green, `doctor_approved: true`, declared placeholders, and en and te blocks with a telegram variant and an email subject and body. Each te block starts with `# needs native-speaker review`.
- Add `fixtures/text_bank.json`: 30 fictional patient replies (with intent and topic) and 30 fictional doctor-facing drafts.
- Add `scripts/banned_terms.py`: scans the templates, the patient replies in the text bank, `web/src/pages/PatientApp`, `web/src/pages/Supporter` and `web/src/components/i18n*`. Exit 1 with file and line on a hit. Word-boundary matching.
- Add `data/guidelines/README.md` as a stub.
- Add `tests/unit/content/` (template structure, text bank counts, scanner behaviour and a clean-repo check).

Owning lane: K (content). Spec section: feature_specs/01_channels_intake.md, "Templates (EN; TE/HI only from doctor-approved translations)" and the Content test line, plus the 03 template rules.

## Out of scope

- Hindi templates (TE only in this change, per the lane brief).
- Editing `cm/router/templates.py` (the loader, lane F), the Makefile (L0), `web/` (other lanes), or `cm/contracts/` (frozen).
- Doctor approval of the Telugu wording (machine-written; flagged for native-speaker review).
- A `scripts/README` file; none exists, so the `banned-terms` hint is in the scanner docstring.
