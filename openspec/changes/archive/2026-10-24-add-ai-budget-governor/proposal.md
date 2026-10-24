## Why
Spend caps and provider limits must degrade the system, not kill it (AI_LIMITS_AND_CAPS.md).

## What Changes
- Add budget governor, circuit breaker, retry/limiter/fallback, governed get_model, PII guard, lifecycle flag, alerts, admin usage numbers.
- Lane A (cm/core). Contracts untouched. Implements AI_LIMITS_AND_CAPS sections 3 and 5.
- Out of scope: sending alerts, DB-backed store, UI panel, runtime wiring.
