# Lane D: rules notes

## What is here
- `rules_r1.py` .. `rules_r6.py`: one pure `evaluate(events, patient, as_of, thresholds) -> list[Conflict]` per rule.
- `reconcile.py`: `reconcile_frame` (M3, the single implementation), `reconcile(pid, as_of)` (injectable loader; defaults to `cm.store.events_repo.query` + `settings_repo` thresholds), `merge_upsert` (conflicts-table upsert semantics), `open_conflicts`.
- `fast_path.py`: R2/R4 for one event (+ optional prior events). Same conflict ids as the nightly run.
- `drafts.py`: `draft_for_conflict` / `drafts_for_opened` build doctor-only approval drafts (kind `conflict`, no channel, no recipients, deduped on `conflict_id`, every sentence cites `C:` + `E:` refs). Lane E's `cm/agents/gate.py` stores them; nothing in `cm/rules` writes or sends.

## Decisions (where the specs were silent)
- Dates are IST calendar dates. Visible at `as_of` = `occurred <= as_of and recorded <= as_of`; tombstones and superseded events (same patient only) are dropped.
- Conflicts returned include closed ones known at `as_of` (`closed_as_of` set), so the nightly upsert and the evaluator see history.
- R1: ledger in days of cover; a dispense counts from `max(occurred, recorded)` so chemist lag never creates a gap after the fact. Daily dose from the latest dispense with `tablets` and `days_supply`, else 4 tablets/day. No dispense at all means R1 abstains. "Taken" = self-reported, non-proxy, >= 3 distinct days in the gap.
- R2: no RegimenChange known means first-line (fail safe, Red).
- R3 (a) opens at `paid_on + 30` when a not-received report dated on/after `paid_on` is not resolved by then; (b) opens when the first non-paid portal record for a month is more than 60 days old.
- R5: check-in days strictly before `as_of`; a witnessed/told Supporter visit since the previous check-in day counts as contact. Red at `r5_red_streak` (same conflict id, tier escalates).
- R6: day-by-day sweep on recorded knowledge from `contacts_due_day`; actions `screened|flagged|referred|doctor_decision` count as screened; `ContextNote{kind: household_declined}` suppresses (closes an open one). Anchor = first RegimenChange, else PortalRegistration, else `start:{date}`.

## Open issues
- `reconcile()` derives the patient context from events (no patient repo in `cm/store` yet). Pass `patient=` when a repo exists.
- `drafts_for_opened` does not re-draft on an Amber to Red escalation (R5); the sweeper or gate may want that.
- No Protocol fake yet: the real functions are pure and cheap, so tests use them directly.

## Verification
`pytest tests/unit/rules tests/redteam -q` (unit cases per rule, determinism under shuffle, 150-seed fuzz, import scan: no send path, no LLM).
