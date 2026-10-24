"""Lane D: R3 payment (Amber). 02 F6, arch §3.4.

(a) Paid but not received: the portal says month ``M`` was ``paid`` on ``P``, and a patient or
Supporter ``PaymentReport`` for ``M`` dated on/after ``P`` says ``not_received``, with no
``received`` report for ``M`` before ``P + 30``. Opens at ``P + 30``; closes when a
``received`` report for ``M`` is recorded.
(b) Support unpaid: the first non-paid ``PortalPayment`` for ``M`` is more than 60 days old and
no ``paid`` record for ``M`` is known. Closes when a ``paid`` record for ``M`` is recorded.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from cm.contracts.admin import RuleThresholds
from cm.contracts.memory import Conflict

from ._common import Ctx, Ev, make_conflict, pdate, prepare

RULE = "R3"
NOT_RECEIVED_DAYS = 30
UNPAID_DAYS = 60


def _by_month(evs: list[Ev]) -> dict[str, list[Ev]]:
    out: dict[str, list[Ev]] = {}
    for e in evs:
        m = e.get("month")
        if isinstance(m, str):
            out.setdefault(m, []).append(e)
    return out


def _paid_not_received(ctx: Ctx, paid: Ev, reports: list[Ev]) -> Conflict | None:
    p = pdate(paid, "paid_on") or paid.occurred
    due = p + timedelta(days=NOT_RECEIVED_DAYS)
    nr = [r for r in reports if r.get("status") == "not_received" and r.occurred >= p]
    if not nr or due > ctx.as_of:
        return None
    rec = sorted(
        (r for r in reports if r.get("status") == "received" and r.occurred >= nr[0].occurred),
        key=lambda r: (r.recorded, r.event_id),
    )
    if rec and rec[0].recorded <= due:
        return None
    opened = max(due, nr[0].recorded)
    if opened > ctx.as_of:
        return None
    closed = rec[0].recorded if rec else None
    if closed is not None and closed <= opened:
        return None  # "received" was already known before the conflict could open: never open
    title = (
        f"Portal shows the {paid.get('month')} support paid on day {ctx.day(p)}; "
        f"{len(nr)} report(s) say not received for {NOT_RECEIVED_DAYS}+ days."
    )
    return make_conflict(
        ctx,
        rule=RULE,
        tier="amber",
        anchor=paid.event_id,
        title=title,
        evidence=[paid, *nr, *rec[:1]],
        opened=opened,
        closed=closed,
    )


def _unpaid(ctx: Ctx, month: str, portal: list[Ev]) -> Conflict | None:
    pending = [e for e in portal if e.get("status") in ("pending", "unpaid", "failed")]
    if not pending:
        return None
    first = pending[0]
    due = first.occurred + timedelta(days=UNPAID_DAYS + 1)  # "more than 60 days"
    paid = sorted(
        (e for e in portal if e.get("status") == "paid"), key=lambda e: (e.recorded, e.event_id)
    )
    if due > ctx.as_of or (paid and paid[0].recorded <= due):
        return None
    closed = paid[0].recorded if paid else None
    title = f"Support for {month} not paid {UNPAID_DAYS}+ days after day {ctx.day(first.occurred)}."
    return make_conflict(
        ctx,
        rule=RULE,
        tier="amber",
        anchor=first.event_id,
        title=title,
        evidence=[*pending, *paid[:1]],
        opened=due,
        closed=closed,
    )


def evaluate(
    events: Any, patient: Any, as_of: date, thresholds: RuleThresholds | None = None
) -> list[Conflict]:
    """Rule R3."""
    ctx = prepare(events, patient, as_of, thresholds)
    portal = _by_month(ctx.of_type("PortalPayment"))
    reports = _by_month(ctx.of_type("PaymentReport"))
    out: list[Conflict | None] = []
    for month in sorted(portal):
        for paid in (e for e in portal[month] if e.get("status") == "paid"):
            out.append(_paid_not_received(ctx, paid, reports.get(month, [])))
            break  # one paid record per month anchors part (a)
        out.append(_unpaid(ctx, month, portal[month]))
    return [c for c in out if c is not None]
