"""Lane D: R1 refill vs self-report (Amber). 02 F6, arch §3.4.

Supply ledger ``on_hand(d) = sum(dispensed supply known by d) - (d - treatment_start)`` in
days of cover, where a dispense is *known* from ``max(occurred, recorded)``. On each day this
equals what the system could see then, so a dispense recorded late by the chemist (lag) never
creates a gap after the fact, and a gap opened before a late record closes on its record date. A dispense with ``days_supply`` covers that many days; otherwise
``tablets / daily_dose`` days, where ``daily_dose`` comes from the latest dispense that has
both values (else :data:`DEFAULT_DAILY_DOSE`). R1 fires for a gap ``[g, h]`` (on_hand <= 0)
from ``g + LAG`` (and the third report) and the patient self-reported "taken" on >= 3 distinct days in the gap.
It closes when a dispense covering the gap is recorded. R1 abstains with no dispense at all
(no chemist feed is an unknown, not a contradiction).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from cm.contracts.admin import RuleThresholds
from cm.contracts.memory import Conflict

from ._common import Ctx, Ev, days, make_conflict, pdate, prepare

RULE = "R1"
LAG_DAYS = 3
"""Chemist CSV lag tolerated before a gap counts (02 F6)."""
MIN_TAKEN_DAYS = 3
DEFAULT_DAILY_DOSE = 4.0
"""Tablets per day when no dispense carries ``days_supply`` (fixed-dose combination, mid weight band)."""


def _num(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def daily_dose(dispenses: list[Ev]) -> float:
    for e in reversed(dispenses):
        tabs, supply = _num(e.get("tablets")), _num(e.get("days_supply"))
        if tabs and supply and tabs > 0 and supply > 0:
            return tabs / supply
    return DEFAULT_DAILY_DOSE


def supply_days(e: Ev, dose: float) -> float:
    supply = _num(e.get("days_supply"))
    if supply is not None and supply > 0:
        return supply
    return max(_num(e.get("tablets")) or 0.0, 0.0) / dose


def known(e: Ev) -> date:
    return max(e.occurred, e.recorded)


def supply_ledger(ctx: Ctx) -> dict[date, float]:
    """Days of cover left on each calendar day from treatment start to as_of (deterministic)."""
    disp = ctx.of_type("Dispense")
    dose = daily_dose(disp)
    by_day: dict[date, float] = {}
    for e in disp:
        by_day[known(e)] = by_day.get(known(e), 0.0) + supply_days(e, dose)
    before = sum(v for d, v in by_day.items() if d < ctx.treatment_start)
    ledger, total = {}, before
    for d in days(ctx.treatment_start, ctx.as_of):
        total += by_day.get(d, 0.0)
        ledger[d] = round(total - ctx.day(d), 6)
    return ledger


def _gaps(ledger: dict[date, float]) -> list[tuple[date, date]]:
    runs: list[tuple[date, date]] = []
    start: date | None = None
    prev: date | None = None
    for d in sorted(ledger):
        if ledger[d] <= 0:
            start = start or d
        elif start is not None and prev is not None:
            runs.append((start, prev))
            start = None
        prev = d
    if start is not None and prev is not None:
        runs.append((start, prev))
    return runs


def _taken_in(ctx: Ctx, g: date, h: date) -> list[Ev]:
    out = []
    for e in ctx.of_type("DoseCheckin"):
        fd = pdate(e, "for_date")
        if (
            e.reporter_mode == "self"
            and e.get("status") == "taken"
            and not e.get("proxy")
            and fd
            and g <= fd <= h
        ):
            out.append(e)
    return sorted(out, key=lambda e: (e.recorded, e.occurred, e.event_id))


def _episode(ctx: Ctx, g: date, h: date) -> Conflict | None:
    taken = _taken_in(ctx, g, h)
    taken_days: list[date] = []
    third: Ev | None = None
    for e in taken:
        fd = pdate(e, "for_date")
        if fd not in taken_days:
            taken_days.append(fd)
            if len(taken_days) == MIN_TAKEN_DAYS:
                third = e
    if third is None:
        return None
    opened = max(g + timedelta(days=LAG_DAYS), third.recorded)
    disp = ctx.of_type("Dispense")
    closing = [e for e in disp if g <= known(e) <= h + timedelta(days=1)] if h < ctx.as_of else []
    closed = h + timedelta(days=1) if closing else None
    if opened > ctx.as_of or (closed is not None and closed <= opened):
        return None
    last = [e for e in disp if known(e) < g]
    anchor_ev = last[-1] if last else taken[0]
    bought = f"day {ctx.day(min(e.occurred for e in closing))}" if closing else "not yet"
    title = f"Refill due day {ctx.day(g)}, bought {bought}; {len(taken_days)} 'Taken' reports in between."
    evidence = ([anchor_ev] if last else []) + closing + taken
    return make_conflict(
        ctx,
        rule=RULE,
        tier="amber",
        anchor=anchor_ev.event_id,
        title=title,
        evidence=evidence,
        opened=opened,
        closed=closed,
    )


def evaluate(
    events: Any, patient: Any, as_of: date, thresholds: RuleThresholds | None = None
) -> list[Conflict]:
    """Rule R1: refill gap while self-reporting taken."""
    ctx = prepare(events, patient, as_of, thresholds)
    if not ctx.of_type("Dispense"):
        return []
    out = [_episode(ctx, g, h) for g, h in _gaps(supply_ledger(ctx))]
    return [c for c in out if c is not None]
