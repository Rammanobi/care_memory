"""Plain-Python patient features (no LLM, no randomness). Numbers shown or cited anywhere come from here.

Input is a list of event dicts as returned by ``cm.store.events_repo.query`` (already as_of-filtered by the
store; this module filters again so a bad caller cannot leak the future). Output is a ``PatientFeatures``.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30))
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
PATIENT_SOURCES = {"web", "telegram", "supporter", "whatsapp", "app"}
WINDOWS = (3, 7)
_RAN_OUT = re.compile(r"ran out around day (\d+)", re.I)


def cite_id(event: dict[str, Any]) -> str:
    """Short, stable citation id for an event: E- plus the first 8 hex digits of its uuid."""
    return "E-" + str(event["event_id"]).replace("-", "")[:8]


def _day(ts: datetime) -> date:
    return ts.astimezone(IST).date()


@dataclass
class PatientFeatures:
    """Everything the narrator may state. ``numbers`` are the only digits a sentence may contain."""

    as_of: date
    missed_3d: int = 0
    missed_7d: int = 0
    taken_7d: int = 0
    longest_streak: int = 0
    weekday_misses: dict[str, int] = field(default_factory=dict)
    top_miss_weekday: str | None = None
    refill_gap_days: int = 0
    quiet_days: int = 0
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    checkins_total: int = 0
    # feature name -> citation ids of the events that back it
    cites: dict[str, list[str]] = field(default_factory=dict)

    @property
    def numbers(self) -> dict[str, int]:
        n = {
            "missed_3d": self.missed_3d, "missed_7d": self.missed_7d, "taken_7d": self.taken_7d,
            "longest_streak": self.longest_streak, "refill_gap_days": self.refill_gap_days,
            "quiet_days": self.quiet_days, "checkins_total": self.checkins_total,
        }
        if self.top_miss_weekday:
            n["top_miss_count"] = self.weekday_misses[self.top_miss_weekday]
        for w in WINDOWS:
            n[f"window_{w}"] = w
        return n

    @property
    def event_ids(self) -> set[str]:
        return {c for cs in self.cites.values() for c in cs}

    def as_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of.isoformat(), **self.numbers, "weekday_misses": self.weekday_misses,
            "top_miss_weekday": self.top_miss_weekday, "conflicts": self.conflicts, "cites": self.cites,
        }


def _checkins(events: Iterable[dict[str, Any]]) -> dict[date, dict[str, Any]]:
    """One check-in per IST day (latest wins); 'for_date' in the payload overrides the event date."""
    by_day: dict[date, dict[str, Any]] = {}
    evs = list(events)
    superseded = {e["supersedes"] for e in evs if e.get("supersedes")}
    live = (e for e in evs if e["type"] == "DoseCheckin" and e["event_id"] not in superseded
            and (e.get("payload") or {}).get("status") != "undone")  # undone = no dose recorded
    for e in sorted(live, key=lambda x: x["occurred_at"]):
        raw = (e.get("payload") or {}).get("for_date")
        d = date.fromisoformat(raw) if raw else _day(e["occurred_at"])
        by_day[d] = e
    return by_day


def _streak(by_day: dict[date, dict[str, Any]]) -> int:
    best = run = 0
    prev: date | None = None
    for d in sorted(by_day):
        if by_day[d]["payload"].get("status") == "taken":
            run = run + 1 if prev is not None and (d - prev).days == 1 else 1
            prev = d
            best = max(best, run)
        else:
            run, prev = 0, None
    return best


def _supply_end(e: dict[str, Any], day0: date | None) -> date | None:
    p = e.get("payload") or {}
    if isinstance(p.get("days_supply"), int):
        return _day(e["occurred_at"]) + timedelta(days=p["days_supply"])
    m = _RAN_OUT.search(str(p.get("why", "")))
    if m and day0:
        return day0 + timedelta(days=int(m.group(1)))
    return None


def compute_features(events: Iterable[dict[str, Any]], as_of: datetime, day0: date | None = None) -> PatientFeatures:
    """Pure function. ``day0`` (sim day 0 date) is only needed to read 'ran out around day N' chemist notes."""
    evs = [e for e in events if e["occurred_at"] <= as_of and e["recorded_at"] <= as_of]
    today = _day(as_of)
    f = PatientFeatures(as_of=today)
    by_day = _checkins(evs)
    f.checkins_total = len(by_day)
    f.longest_streak = _streak(by_day)
    miss_c: Counter[int] = Counter()
    for d, e in by_day.items():
        age = (today - d).days
        status = e["payload"].get("status")
        if status == "missed":
            miss_c[d.weekday()] += 1
            for w in WINDOWS:
                if 0 <= age < w:
                    setattr(f, f"missed_{w}d", getattr(f, f"missed_{w}d") + 1)
                    f.cites.setdefault(f"missed_{w}d", []).append(cite_id(e))
        elif status == "taken" and 0 <= age < 7:
            f.taken_7d += 1
            f.cites.setdefault("taken_7d", []).append(cite_id(e))
    f.weekday_misses = {WEEKDAYS[k]: v for k, v in sorted(miss_c.items())}
    if miss_c and max(miss_c.values()) >= 2:
        k = min(k for k, v in miss_c.items() if v == max(miss_c.values()))
        f.top_miss_weekday = WEEKDAYS[k]
        f.cites["weekday_pattern"] = [cite_id(e) for d, e in by_day.items() if d.weekday() == k and e["payload"].get("status") == "missed"]
    # refill gap: days past the end of the latest known supply
    ends = [(end, e) for e in evs if e["type"] == "Dispense" and (end := _supply_end(e, day0))]
    if ends:
        end, e = max(ends, key=lambda x: x[0])
        f.refill_gap_days = max(0, (today - end).days)
        if f.refill_gap_days:
            f.cites["refill_gap_days"] = [cite_id(e)]
    # quiet days: days since any patient-side event
    mine = [e for e in evs if e.get("source") in PATIENT_SOURCES and e["type"] in {"DoseCheckin", "ContextNote"}]
    if mine:
        last = max(mine, key=lambda x: x["occurred_at"])
        f.quiet_days = max(0, (today - _day(last["occurred_at"])).days)
        if f.quiet_days:
            f.cites["quiet_days"] = [cite_id(last)]
    # conflict: self-report says taken, supply says there was nothing to take
    if f.refill_gap_days > 0 and f.taken_7d >= 3:
        f.conflicts.append({
            "kind": "self_report_vs_refill",
            "taken_7d": f.taken_7d, "refill_gap_days": f.refill_gap_days,
            "cites": f.cites.get("taken_7d", [])[:3] + f.cites.get("refill_gap_days", []),
        })
    return f


def suggest_tier(f: PatientFeatures) -> str:
    """Review tier for the nightly card. Deterministic; rules lane may replace it later."""
    if f.missed_3d >= 3 or (f.refill_gap_days >= 7 and f.missed_7d >= 3):
        return "red"
    if f.missed_7d >= 2 or f.refill_gap_days > 0 or f.conflicts:
        return "amber"
    return "green"
