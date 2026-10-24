# fix-invariant-bugs

## Why
A pre-push high-end test pass (property, DB-invariant, concurrency and API-contract tests under
`tests/property/`, `tests/invariants/`, `tests/concurrency/`, `tests/contract/test_api_contract.py`)
found real bugs in non-AI code. Pure bug fixes; intended behaviour is unchanged (skip_specs).

## What Changes
Each fix: symptom, root cause, fix, verification.

1. **Tokenizer leaked phones and Aadhaar numbers** (lane A, `cm/core/tokenize.py`).
   Symptom: `600 000 0000`, `09876543210`, `2000-0000-0000`, `200000000000` reached the prompt untouched
   and `assert_clean` passed. Cause: PHONE allowed only 5-5 grouping and no `0` trunk prefix; AADHAAR only
   space-separated. Fix: PHONE accepts `+91`/`91`/`0` prefixes and any single space/hyphen grouping;
   AADHAAR accepts space, hyphen or no separator. Verified: `tests/property/test_core_props.py`.
2. **Retry slept `nan` seconds** (lane A, `cm/core/retry.py`). A `Retry-After: nan` header made
   `call_with_retry` call `sleep(nan)` (ValueError escapes the retry wrapper). Fix: non-finite values are
   ignored (backoff is used). Verified: `test_any_retry_after_header_sleeps_a_finite_nonnegative_time`.
3. **Budget day was the UTC date** (lane A, `cm/core/budget.py`, `cm/core/budget_pg.py`).
   `BudgetGovernor.today()` used `clock().date()` (UTC by default), and `PgUsageStore.task_cost` built the
   ad-hoc row id from the UTC date while `add()` used the IST day, so between 00:00 and 05:30 IST the
   per-task cap read the wrong row. Fix: both use the IST date. Verified: `test_budget_day_is_the_ist_date`,
   `test_new_ist_day_resets_state_and_alerts_fire_once`, `test_pg_budget_store_task_cost_uses_the_ist_day`.
4. **Refill gap used UTC dates** (lane C, `cm/memory/detectors/refill.py`). `refill_coverage` disagreed
   with `compute_features` by one day around IST midnight. Fix: `ist_date()`. Verified:
   `test_refill_detector_agrees_with_features_on_ist_days`.
5. **Features depended on input order** (lane C, `cm/memory/features.py`). Two check-ins with the same
   `occurred_at` resolved by list order (`taken_7d` changed under shuffle). Fix: tie-break on
   `recorded_at`, then `event_id`. Verified: `test_features_shuffle_invariant`.
6. **`events_repo.missed_days` ignored `recorded_at`** (lane A, `cm/store/events_repo.py`). A miss
   recorded after `until` was counted (non-negotiable 9). Fix: `AND recorded_at <= until`. Verified:
   `test_missed_days_respects_recorded_at`.
7. **Outbox doctor gate had two DB-level holes** (lane A, new migration
   `cm/store/migrations/0010_outbox_gate_hardening.sql`; 0009 is reserved for rag_v2).
   (a) a system-kind row with a DRAFT template was accepted when it also carried any approve
   `decision_id`; (b) the `body` of an authorised row could be rewritten afterwards. Fix: the template must
   be approved whenever the row relies on the template branch; a new trigger freezes `body` (only the purge
   to NULL is allowed). Verified: `test_gate_rejects_every_unauthorised_insert`,
   `test_gate_cannot_be_bypassed_by_update`.

8. **R5 rewrote history on late records** (lane D, `cm/rules/rules_r5.py`). A prompt or reply recorded
   days late moved an earlier `opened_as_of`, or erased a conflict that had been open on the record
   (hindsight evaluation). Fix: R5 is swept day by day over what was known on each day (as R6 already is);
   a conflict erased by a late record is closed on the record day. Existing R5 unit/red-team tests unchanged.
   Verified: `tests/property/test_rules_props.py::test_as_of_monotonic_history_is_stable`.
9. **R3 produced an inverted interval** (lane D, `cm/rules/rules_r3.py`). When the `not_received` report was
   recorded after the 30-day due date and a `received` report was recorded before that, the conflict had
   `closed_as_of < opened_as_of`. Fix: such a conflict never opens. Verified:
   `test_as_of_bounds_and_evidence_is_visible`.

## Out of scope
- `cm.allow_erasure` is a plain custom GUC, so any session can `SET LOCAL` it and bypass the append-only
  triggers; hardening needs a SECURITY DEFINER design for `cm.erase_person()` (reported, not changed).
- Double-tap on a Telegram button stores two raw `DoseCheckin` events (idempotency key is per update);
  readers collapse them per day and the fast path dedupes drafts per day, so no behaviour change here.

## Owning lanes
A (core, store, migration), C (memory), D (rules R3/R5). Logged by the test agent under MEMORY.md Rule 1.
