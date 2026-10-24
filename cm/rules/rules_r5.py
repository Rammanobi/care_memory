"""Lane D: R5 non-response streak (Amber, Red at ``r5_red_streak``). 02 F6, arch §3.4, E1.

Check-in days are the distinct ``CheckinPrompt.for_date`` values strictly before ``as_of``
(today's prompt may still be answered). A day is answered when a ``DoseCheckin`` exists for
that ``for_date`` (or answers that prompt's ``outbox_id``), or a Supporter made contact
(``SupporterVisit`` witnessed/told) after the previous check-in day and up to this one.
A run of ``r5_amber_streak`` unanswered days opens a conflict anchored on the run's first
prompt; the tier is Red once the run reaches ``r5_red_streak``. The next answered day closes it.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from cm.contracts.admin import RuleThresholds
from cm.contracts.memory import Conflict

from ._common import Ctx, Ev, make_conflict, pdate, prepare

RULE = "R5"


def _answers(
    ctx: Ctx, prompts_by_day: dict[date, list[Ev]]
) -> tuple[dict[date, date], list[tuple[date, date]]]:
    """(checkin day -> earliest recorded answer, [(contact day, recorded)])."""
    outbox_day = {str(p.get("outbox_id")): d for d, ps in prompts_by_day.items() for p in ps}
    answered: dict[date, date] = {}
    for e in ctx.of_type("DoseCheckin"):
        d = pdate(e, "for_date")
        if e.get("prompt_outbox_id") is not None:
            d = outbox_day.get(str(e.get("prompt_outbox_id")), d)
        if d is not None:
            answered[d] = min(answered.get(d, e.recorded), e.recorded)
    contacts = [
        (pdate(e, "visit_date") or e.occurred, e.recorded)
        for e in ctx.of_type("SupporterVisit")
        if e.get("mode") in ("witnessed", "told")
    ]
    return answered, contacts


def _runs(ctx: Ctx) -> list[tuple[list[date], date | None, dict[date, list[Ev]]]]:
    by_day: dict[date, list[Ev]] = {}
    for p in ctx.of_type("CheckinPrompt"):
        d = pdate(p, "for_date") or p.occurred
        if d < ctx.as_of:
            by_day.setdefault(d, []).append(p)
    answered, contacts = _answers(ctx, by_day)
    runs, cur, prev = [], [], None
    for d in sorted(by_day):
        hits = [r for c, r in contacts if (prev is None or c > prev) and c <= d]
        if d in answered:
            hits.append(answered[d])
        if hits:
            if cur:
                runs.append((cur, min(hits), by_day))
            cur = []
        else:
            cur.append(d)
        prev = d
    if cur:
        runs.append((cur, None, by_day))
    return runs


def evaluate(
    events: Any, patient: Any, as_of: date, thresholds: RuleThresholds | None = None
) -> list[Conflict]:
    """Rule R5."""
    ctx = prepare(events, patient, as_of, thresholds)
    amber, red = ctx.thresholds.r5_amber_streak, ctx.thresholds.r5_red_streak
    out: list[Conflict] = []
    for run, closed, by_day in _runs(ctx):
        if len(run) < amber:
            continue
        opened = run[amber - 1] + timedelta(days=1)
        if closed is not None and closed <= opened:
            continue
        prompts = [
            p for d in run for p in sorted(by_day[d], key=lambda e: (e.recorded, e.event_id))
        ]
        tier = "red" if len(run) >= red else "amber"
        title = (
            f"{len(run)} check-ins in a row with no reply and no Supporter contact "
            f"(day {ctx.day(run[0])} to day {ctx.day(run[-1])})."
        )
        out.append(
            make_conflict(
                ctx,
                rule=RULE,
                tier=tier,
                anchor=prompts[0].event_id,
                title=title,
                evidence=prompts,
                opened=opened,
                closed=closed,
            )
        )
    return out
