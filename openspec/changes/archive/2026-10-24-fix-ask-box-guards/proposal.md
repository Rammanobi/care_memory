## Why
Lane G (Core API). AI eval gaps ASK-NO-OUTPUT-GUARD, ASK-PII-ECHO, ASK-ROUTE-SUBSTR, ASK-ROUTE-TE, plus the canned patient answer claiming a draft that may not exist.

## What Changes
- Symptom: model answers reached the doctor with dosing advice or obeyed injections; phone/email/Aadhaar from notes echoed; "need a refill" routed to the red list; Telugu list questions unrouted; false "draft waiting".
- Root cause: number-only check, substring regex routing, no masking, English-only keywords, draft claim keyed on needs_me.
- Fix: new cm/api/ask_guard.py (output guard, mask_pii via cm.core.tokenize, word-boundary + Telugu routing); query.py sets refused/refusal_reason; draft claim needs a real pending row.
- Verified: tests/evals, tests/unit/api (new test_ask_guard.py), integration ai_query and edge cases; xfail tags removed, new fixtures added.
- Out of scope: validator, narrator, web, memory, rules. No contract change.
