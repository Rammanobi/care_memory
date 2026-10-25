## Why
Symptom: tests/integration/test_question_research.py errored (7 errors). Root cause: it applied the demo bundle and queried PT-0903/PT-0930, which the seed no longer builds (now PT-0906 6 days, PT-0960 60 days).

## What Changes
Test-only fix: day-3 vs day-60 became PT-0906 vs PT-0960; Telugu tests set PT-0906's vault language to 'te' temporarily (restored in finally, caremem_test only). No product code changed. All assertion intents kept.

Out of scope: product code. Owning lane: Integration. Verified: integration + unit question_research tests, 96 passed.
