## Why
Date labels were off by one day between the sim/IST clock and the real (UTC) clock.

## What Changes
Symptom: IST is +5:30, so between 18:30 and 24:00 UTC the IST date is the next day. Several callers labelled with the UTC date of the clock instant (`at.date()`): `cm/channels/tg_inbound.py` (dose `for_date` fallback), `cm/channels/tg_sender.py` (`sent_today` day and `CheckinPrompt.for_date`), while `outbox_repo.sent_today` and the reminder producer use the IST date. Result: the daily cap and prompt dates were a day behind the IST day.

Root cause: no shared IST date helper in `cm/core/clock.py`; callers used `.date()` on a UTC instant. `clock.sim_instant` itself is correct (day N = day0 + N days at 18:00 IST, no offset).

Fix: add `clock.ist_date(at)` and use it in `tg_inbound.py` and `tg_sender.py`.

Separate finding (data, not code, not changed): the seeded `cm.sim_clock` has `day0_date=2026-08-27` and `sim_day=59`, so the pinned sim date is 2026-10-25 while the real date was 2026-10-24. A reseed with `DAY0 = date(2026, 8, 26)` in `cm/jobs/seed.py` would align day 59 with that date; not done because it needs `seed --reset` against the live DB.

Verification: `tests/unit/core/test_core.py::test_ist_date_label_is_not_utc_date` (fails without the helper); unit suites for core, store, jobs, channels pass.

## Out of scope
Seed data re-anchoring, budget UTC day (cost accounting is deliberately UTC).

## Owning lane
Sim/Core lane. No change to `cm/contracts/`.
