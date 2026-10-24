"""Engine-level conflicts (1.3): pure functions, deterministic ids, ``C:`` refs. No I/O, no clock, no LLM.

These are memory-engine contradictions computed from check-ins, refill coverage and weekday beliefs. They are
separate from the R1-R6 reconciler rows in ``cm.conflicts`` (that table's ``rule`` column only allows R1-R6);
the pipeline returns them in the snapshot and stores them with the features row.

* ``self_report_vs_refill``: the patient self-reports "taken" on >= 3 days after the latest supply ran out.
* ``weekday_pattern_conflict``: a weekday flagged as a miss day (hypothesis or confirmed) whose last two
  instances were both reported "taken", so the recent self-report contradicts the stored pattern.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid5

from cm.core.clock import ist_date
from cm.memory.detectors.refill import refill_coverage
from cm.memory.features import PATIENT_SOURCES, WEEKDAYS, _checkins, cite_id

ENGINE_CONFLICT_NS = UUID("3f1c9a52-7d84-5b0e-a6c1-2e9d4b7f8a13")
"""``conflict_id = uuid5(NS, f"{pid}|{kind}|{anchor}")``. Never change it."""
MIN_TAKEN_DAYS = 3
RECENT_INSTANCES = 2
MAX_EVIDENCE = 6


@dataclass(frozen=True)
class EngineConflict:
    conflict_id: UUID
    kind: str  # self_report_vs_refill | weekday_pattern
    tier: str
    title: str
    refs: tuple[str, ...]  # first "C:<id>", then "E:<event uuid>" evidence
    as_of: date

    @property
    def cref(self) -> str:
        return f"C:{self.conflict_id}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": str(self.conflict_id),
            "kind": self.kind,
            "tier": self.tier,
            "title": self.title,
            "refs": list(self.refs),
            "as_of": self.as_of.isoformat(),
        }


def engine_conflict_id(pid: object, kind: str, anchor: str) -> UUID:
    return uuid5(ENGINE_CONFLICT_NS, f"{pid}|{kind}|{anchor}")


def _visible(events: Iterable[dict[str, Any]], as_of: datetime) -> list[dict[str, Any]]:
    return [e for e in events if e["occurred_at"] <= as_of and e["recorded_at"] <= as_of]


def _self_reported(e: dict[str, Any]) -> bool:
    return e.get("source") in PATIENT_SOURCES and e.get("reporter_mode", "self") not in (
        "witnessed",
        "told",
        "proxy",
    )


def _eref(e: dict[str, Any]) -> str:
    return f"E:{e['event_id']}"


def self_report_vs_refill(
    pid: object, as_of: datetime, events: Iterable[dict[str, Any]]
) -> EngineConflict | None:
    evs = _visible(events, as_of)
    cov = refill_coverage(evs, as_of)
    if cov.supply_end is None or cov.gap_days <= 0:
        return None
    taken = [
        e
        for d, e in sorted(_checkins(evs).items())
        if d >= cov.supply_end
        and d <= ist_date(as_of)
        and e["payload"].get("status") == "taken"
        and _self_reported(e)
    ]
    if len(taken) < MIN_TAKEN_DAYS:
        return None
    disp = [e for e in evs if e["type"] == "Dispense" and cite_id(e) in cov.cites]
    refs = [_eref(e) for e in disp[:1] + taken[:MAX_EVIDENCE]]
    cid = engine_conflict_id(pid, "self_report_vs_refill", cov.supply_end.isoformat())
    title = f"Reported taking doses on {len(taken)} days, but supply ended {cov.gap_days} days ago"
    return EngineConflict(
        cid, "self_report_vs_refill", "amber", title, (f"C:{cid}", *refs), ist_date(as_of)
    )


def weekday_pattern_conflict(
    pid: object, as_of: datetime, events: Iterable[dict[str, Any]], active_weekdays: Iterable[str]
) -> list[EngineConflict]:
    """``active_weekdays`` are weekday names (e.g. 'Thursday') whose belief is hypothesis or confirmed."""
    evs = _visible(events, as_of)
    by_day = _checkins(evs)
    out: list[EngineConflict] = []
    for wd in sorted(set(active_weekdays), key=WEEKDAYS.index):
        k = WEEKDAYS.index(wd)
        inst = [
            (d, e) for d, e in sorted(by_day.items()) if d.weekday() == k and d <= ist_date(as_of)
        ]
        last = inst[-RECENT_INSTANCES:]
        if len(last) < RECENT_INSTANCES or any(
            e["payload"].get("status") != "taken" for _, e in last
        ):
            continue
        misses = [e for _, e in inst if e["payload"].get("status") == "missed"]
        if not misses:
            continue
        anchor = f"{wd}:{last[0][0].isoformat()}"
        cid = engine_conflict_id(pid, "weekday_pattern", anchor)
        refs = [_eref(e) for _, e in last] + [_eref(e) for e in misses[-3:]]
        title = f"{wd} was flagged as a missed day, but the last {RECENT_INSTANCES} {wd}s were reported taken"
        out.append(
            EngineConflict(
                cid, "weekday_pattern", "green", title, (f"C:{cid}", *refs), ist_date(as_of)
            )
        )
    return out
