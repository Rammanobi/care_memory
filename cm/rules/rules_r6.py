"""Lane D: R6 contacts not screened (Amber, P0). INTEGRATION_DECISIONS §a4 M8, arch §3.4.

From treatment day ``contacts_due_day`` (``RuleThresholds``, default 14) R6 holds when the
patient has zero listed household contacts, or any listed contact is not yet screened.
A ``ContextNote{kind:"household_declined"}`` suppresses it. It closes when every listed
contact is screened. The state is swept day by day over what was *known* (recorded) on each
day, so ``opened_as_of``/``closed_as_of`` are exact and replays are deterministic.

Anchor: the treatment-start ``RegimenChange`` (else ``PortalRegistration``); without either,
the treatment start date. Names never appear: contacts are counted, never named.
No LLM, no preventive-therapy wording.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from cm.contracts.admin import RuleThresholds
from cm.contracts.memory import Conflict

from ._common import Ctx, Ev, days, make_conflict, prepare

RULE = "R6"
SCREENED_ACTIONS = frozenset({"screened", "flagged", "referred", "doctor_decision"})
"""Actions that imply the screening questions were asked (``screened_at`` set in the projection)."""


@dataclass(frozen=True)
class HouseholdState:
    listed: frozenset[str]
    screened: frozenset[str]
    declined: bool

    @property
    def unscreened(self) -> frozenset[str]:
        return self.listed - self.screened


def household_state(ctx: Ctx, known_on: date) -> HouseholdState:
    """Contacts listed/screened and the decline flag from events known on ``known_on``."""
    listed: set[str] = set()
    screened: set[str] = set()
    declined = False
    for e in ctx.events:
        if max(e.occurred, e.recorded) > known_on:
            continue
        if e.type == "HouseholdContactEvent" and e.get("contact_id") is not None:
            cid = str(e.get("contact_id"))
            listed.add(cid)
            if e.get("action") in SCREENED_ACTIONS:
                screened.add(cid)
        elif e.type == "ContextNote" and e.get("kind") == "household_declined":
            declined = True
    return HouseholdState(frozenset(listed), frozenset(screened), declined)


def fires(st: HouseholdState) -> bool:
    return not st.declined and (not st.listed or bool(st.unscreened))


def _anchor(ctx: Ctx) -> tuple[str, list[Ev]]:
    for kind in ("RegimenChange", "PortalRegistration"):
        evs = ctx.of_type(kind)
        if evs:
            return evs[0].event_id, [evs[0]]
    return f"start:{ctx.treatment_start.isoformat()}", []


def _sweep(ctx: Ctx, due: date) -> tuple[date | None, date | None]:
    """(first opened, closed-on if not open at as_of)."""
    opened: date | None = None
    open_now, closed = False, None
    for d in days(due, ctx.as_of):
        f = fires(household_state(ctx, d))
        if f and not open_now:
            opened = opened or d
            closed = None
        elif not f and open_now:
            closed = d
        open_now = f
    return opened, closed


def evaluate(
    events: Any, patient: Any, as_of: date, thresholds: RuleThresholds | None = None
) -> list[Conflict]:
    """Rule R6, contacts not screened."""
    ctx = prepare(events, patient, as_of, thresholds)
    due_day = ctx.thresholds.contacts_due_day
    due = ctx.treatment_start + timedelta(days=due_day)
    if due > as_of:
        return []
    opened, closed = _sweep(ctx, due)
    if opened is None:
        return []
    st = household_state(ctx, as_of)
    if not st.listed:
        title = f"No household contacts listed by treatment day {due_day}."
    else:
        title = f"{len(st.unscreened)} of {len(st.listed)} household contacts not screened (due day {due_day})."
    if closed is not None:
        title = (
            f"Household screening declined (noted day {ctx.day(closed)})."
            if st.declined
            else f"Household contacts: {len(st.screened & st.listed)} of {len(st.listed)} screened."
        )
    anchor, start_evs = _anchor(ctx)
    contact_evs = [
        e
        for e in ctx.events
        if e.type == "HouseholdContactEvent"
        or (e.type == "ContextNote" and e.get("kind") == "household_declined")
    ]
    return [
        make_conflict(
            ctx,
            rule=RULE,
            tier="amber",
            anchor=anchor,
            title=title,
            evidence=[*start_evs, *contact_evs],
            opened=opened,
            closed=closed,
        )
    ]
