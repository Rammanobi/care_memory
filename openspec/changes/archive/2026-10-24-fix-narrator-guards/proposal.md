## Why
Two open bugs from the AI eval suite. BANNED-DRIFT: the narrator banned-term list (cm/validator/banned_terms.py) had drifted from cm/router/banned.py (missed lower-case tb, T.B., second-line drugs, MDR/XDR). NARR-CONTENT: cite-or-cut kept grounded sentences that gave dosing advice, a diagnosis or a blaming tone.

## What Changes
- New single lexicon `cm/core/banned_lexicon.py` (disease and drug groups, `audience` patient|doctor; doctor may mention disease words, never drugs). Router and validator both delegate to it.
- New deterministic `cm/validator/content_guard.py` (regex, EN+TE); narrator cuts such sentences with reasons dosing_advice, diagnosis, blame_tone.
- Fixtures: removed known_gap tags (BANNED-DRIFT, NARR-CONTENT) and added cut_reasons; removed the two entries from KNOWN_GAPS.

Lane: AI core / validator. Out of scope: query.py, web, memory, rules. No contract change. Pure bug fix (skip_specs).

## Verification
pytest tests/evals tests/unit/validator tests/unit/ai tests/redteam tests/unit/content tests/unit/router: all narrator and banned cases pass.
