"""Refill coverage and gap (feature_specs/02 F5). Pure; supply end dates come from Dispense events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from cm.memory.features import cite_id


@dataclass(frozen=True)
class RefillCoverage:
    gap_days: int  # days past the end of the latest known supply, 0 if covered
    supply_end: date | None
    covered: bool | None  # None = no dispense known (unknown, never imputed)
    cites: tuple[str, ...]


def refill_coverage(events: list[dict[str, Any]], as_of) -> RefillCoverage:
    """Latest Dispense (occurred and recorded <= as_of) plus ``days_supply`` gives the supply end."""
    best: tuple[date, dict[str, Any]] | None = None
    for e in events:
        if e["type"] != "Dispense" or e["occurred_at"] > as_of or e["recorded_at"] > as_of:
            continue
        ds = (e.get("payload") or {}).get("days_supply")
        if not isinstance(ds, int) or ds < 0:
            continue
        end = e["occurred_at"].date() + timedelta(days=ds)
        if best is None or end > best[0]:
            best = (end, e)
    if best is None:
        return RefillCoverage(0, None, None, ())
    gap = max(0, (as_of.date() - best[0]).days)
    return RefillCoverage(gap, best[0], gap == 0, (cite_id(best[1]),))
