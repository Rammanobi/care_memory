## Why
Symptom: `make banned-terms` pointed at missing tests/unit/router/test_banned_terms.py. Root cause: test lives at tests/unit/content/test_banned_terms.py. Fix: update Makefile path. Verified: target test file runs, 15 passed.

## What Changes
Fix the `banned-terms` Makefile target path.

## Out of scope
Other targets.

## Owning lane
L0 (Makefile). No change to `cm/contracts/`.
