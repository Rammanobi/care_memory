## Why
Rules R1-R6 (including household contact screening R6, P0) and the reconciler are not complete.

## What Changes
Implement R1-R6 in `cm/rules/` and a reconciler that turns rule hits and memory conflicts into approval drafts only.
- Pure `reconcile_frame` (M3), `reconcile(pid, as_of)` with an injectable loader, `merge_upsert`, R2/R4 `fast_path`.
- `drafts.py`: doctor-only conflict drafts (no channel, no recipients) citing `C:` and `E:` refs, deduped on `conflict_id`.
- Tests in `tests/unit/rules/` and red-team tests in `tests/redteam/`.

## Spec section
02 F6 (reconciler), arch §3.4, INTEGRATION_DECISIONS §a4 M3 and M8 (R6, P0).

## Out of scope
Sending messages, UI.

## Owning lane
Lane D (Rules + validator + identity); INTEGRATION_DECISIONS rulings. Only `cm/rules/` and lane D tests change; no `cm/validator/` or `cm/identity/` change was needed. No change to `cm/contracts/`.
