"""Lane D: R2 resistance result vs regimen (Red). 02 F6, arch §3.4, E2.

A ``LabResult`` with ``rif_resistant=True`` fires when the regimen in force at the result's
``recorded_at`` is first-line. The regimen is the latest ``RegimenChange`` known then
(recorded and effective on or before that date). With no regimen record the patient is
assumed first-line (the seed writes one at start; failing safe raises the Red).
The conflict closes when a non-first-line ``RegimenChange`` is recorded after the result.
Also runs on the ingest fast path (see ``fast_path.py``).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from cm.contracts.admin import RuleThresholds
from cm.contracts.memory import Conflict

from ._common import Ctx, Ev, make_conflict, pdate, prepare

RULE = "R2"


def _effective(e: Ev) -> date:
    return pdate(e, "effective_date") or e.occurred


def regimen_at(ctx: Ctx, at: date) -> Ev | None:
    """Latest RegimenChange known and in force on ``at``."""
    known = [e for e in ctx.of_type("RegimenChange") if e.recorded <= at and _effective(e) <= at]
    return max(known, key=lambda e: (_effective(e), e.recorded, e.event_id), default=None)


def _switch_after(ctx: Ctx, at: date) -> Ev | None:
    later = [
        e
        for e in ctx.of_type("RegimenChange")
        if e.get("line") != "first" and (e.recorded >= at and _effective(e) >= at)
    ]
    return min(later, key=lambda e: (e.recorded, e.event_id), default=None)


def check_lab(ctx: Ctx, lab: Ev) -> Conflict | None:
    if lab.type != "LabResult" or lab.get("rif_resistant") is not True:
        return None
    reg = regimen_at(ctx, lab.recorded)
    if reg is not None and reg.get("line") != "first":
        return None
    switch = _switch_after(ctx, lab.recorded)
    closed = switch.recorded if switch is not None else None
    title = (
        f"Resistance result on day {ctx.day(lab.occurred)} while the regimen is still first-line."
    )
    evidence = [lab] + ([reg] if reg else []) + ([switch] if switch else [])
    return make_conflict(
        ctx,
        rule=RULE,
        tier="red",
        anchor=lab.event_id,
        title=title,
        evidence=evidence,
        opened=lab.recorded,
        closed=closed,
    )


def evaluate(
    events: Any, patient: Any, as_of: date, thresholds: RuleThresholds | None = None
) -> list[Conflict]:
    """Rule R2."""
    ctx = prepare(events, patient, as_of, thresholds)
    out = [check_lab(ctx, e) for e in ctx.of_type("LabResult")]
    return [c for c in out if c is not None]
