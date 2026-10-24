"""Lane K: deterministic rendering of events and rollups into short factual sentences for the RAG index.

Rules (RAG_STRATEGY_v2.md section 2, owner decision 3):
- patient token only, never a name; free text comes from ``text_tokenised`` fields (already tokenised);
- lab values, bill numbers, tablet counts and raw CSV rows are never rendered;
- event sentences carry dates but no measurements; numbers appear only on the daily and weekly summary cards,
  and those come from ``cm.memory.features`` (the same numbers are returned in ``numbers`` for ``extra``).
No LLM, no randomness, no clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from cm.memory.features import IST, WEEKDAYS, _checkins, _day, compute_features

RENDER_VERSION = "render-v1"
_STATUS_WORDS = {
    "taken": "taken",
    "missed": "not taken",
    "unwell": "not taken because the patient felt unwell",
    "unclear": "unclear",
    "undone": "withdrawn",
}
_ACTIONS = {
    "approve": "approved",
    "edit": "edited and approved",
    "reject": "rejected",
    "expired": "let expire",
}
_VISIT_MODES = {
    "witnessed": "dose witnessed by the supporter",
    "told": "dose reported to the supporter",
    "unreachable": "patient could not be reached",
}
RENDERED_TYPES = (
    "DoseCheckin",
    "ContextNote",
    "Dispense",
    "LabResult",
    "SupporterVisit",
    "ReviewDecisionEvent",
    "CheckinPrompt",
)


@dataclass(frozen=True)
class Rendered:
    """One rendered event, plus what the indexer needs to build its document row."""

    event_id: str
    event_type: str
    text: str
    occurred_at: datetime
    recorded_at: datetime
    source: str
    doc_type: str  # existing documents.doc_type value (Option A, no schema change)
    author_role: str
    consent_id: Any
    embed: bool  # False: full-text search only (taps carry no free text)
    kind: str = "event"


@dataclass(frozen=True)
class RollupCard:
    kind: str  # "daily" | "weekly"
    text: str
    window_start: datetime
    window_end: datetime  # window close; this is also the recorded_at of the card
    numbers: dict[str, Any]
    source_event_ids: list[str]
    cites: dict[str, list[str]] = field(default_factory=dict)


def _d(value: Any) -> str:
    if isinstance(value, datetime):
        return _day(value).isoformat()
    return str(value)[:10]


def _p(e: dict[str, Any]) -> dict[str, Any]:
    return e.get("payload") or {}


def _dose(e: dict[str, Any], tok: str) -> str:
    p = _p(e)
    day = p.get("for_date") or _d(e["occurred_at"])
    status = p.get("status", "unclear")
    if status == "undone":
        return f"{tok} dose mark for {day} was withdrawn."
    who = "the supporter" if p.get("proxy") or e.get("source") == "supporter" else "the patient"
    late = " (reported late)" if p.get("late") else ""
    return f"{tok} dose for {day} was reported {_STATUS_WORDS.get(status, status)} by {who}{late}."


def _note(e: dict[str, Any], tok: str) -> str:
    p = _p(e)
    origin = {
        "patient_text": "the patient",
        "supporter_text": "the supporter",
        "doctor": "the doctor",
    }.get(p.get("origin", ""), "a user")
    text = (p.get("text_tokenised") or "").strip()
    if not text and isinstance(p.get("data"), dict):
        text = ", ".join(f"{k} {v}" for k, v in sorted(p["data"].items()) if v not in (None, ""))
    if not text:
        text = str(p.get("kind", "note")).replace("_", " ")
    return f"Note from {origin} about {tok} on {_d(e['occurred_at'])}: {text}"


def _dispense(e: dict[str, Any], tok: str) -> str:
    return f"A refill for {tok} was recorded at the chemist on {_d(e['occurred_at'])}."


def _lab(e: dict[str, Any], tok: str) -> str:
    p = _p(e)
    day = p.get("report_date") or _d(e["occurred_at"])
    flag = " It was flagged for doctor review." if p.get("rif_resistant") else ""
    return f"A lab result for {tok} dated {day} was recorded.{flag}"


def _visit(e: dict[str, Any], tok: str) -> str:
    p = _p(e)
    day = p.get("visit_date") or _d(e["occurred_at"])
    if p.get("visit_kind") == "family_screen":
        return f"A supporter household screening visit for {tok} took place on {day}."
    return f"Supporter visit for {tok} on {day}: {_VISIT_MODES.get(p.get('mode', ''), 'visit recorded')}."


def _decision(e: dict[str, Any], tok: str) -> str:
    p = _p(e)
    kind = str(p.get("kind", "review")).replace("_", " ")
    tier = f" {p['tier']}" if p.get("tier") else ""
    reason = (p.get("reason") or "").strip()
    tail = f" Reason: {reason}" if reason else ""
    return f"On {_d(e['occurred_at'])} the doctor {_ACTIONS.get(p.get('action', ''), 'reviewed')} a{tier} {kind} item for {tok}.{tail}"


def _prompt(e: dict[str, Any], tok: str) -> str:
    p = _p(e)
    return f"A dose check-in prompt for {p.get('for_date') or _d(e['occurred_at'])} was sent to {tok} by {e.get('channel') or 'message'}."


_RENDER = {
    "DoseCheckin": _dose,
    "ContextNote": _note,
    "Dispense": _dispense,
    "LabResult": _lab,
    "SupporterVisit": _visit,
    "ReviewDecisionEvent": _decision,
    "CheckinPrompt": _prompt,
}
_DOC = {  # event type -> (documents.doc_type, author_role)
    "DoseCheckin": ("checkin", "patient"),
    "ContextNote": ("supporter_note", "doctor"),  # refined per origin below
    "Dispense": ("sales_csv", "chemist"),
    "LabResult": ("lab", "lab"),
    "SupporterVisit": ("checkin", "supporter"),
    "ReviewDecisionEvent": ("supporter_note", "doctor"),
    "CheckinPrompt": ("checkin", "system"),
}


def _doc_meta(e: dict[str, Any]) -> tuple[str, str]:
    doc_type, role = _DOC[e["type"]]
    if e["type"] == "ContextNote":
        origin = _p(e).get("origin")
        if origin == "patient_text":
            return "checkin", "patient"
        if origin == "supporter_text":
            return "supporter_note", "supporter"
    if e["type"] == "DoseCheckin" and (_p(e).get("proxy") or e.get("source") == "supporter"):
        role = "supporter"
    return doc_type, role


def render_event(e: dict[str, Any], token: str) -> Rendered | None:
    """Render one event dict (as returned by ``events_repo.query``). Unsupported types return None."""
    fn = _RENDER.get(e["type"])
    if fn is None:
        return None
    doc_type, role = _doc_meta(e)
    has_free_text = e["type"] in (
        "ContextNote",
        "ReviewDecisionEvent",
        "LabResult",
        "SupporterVisit",
    )
    return Rendered(
        event_id=str(e["event_id"]),
        event_type=e["type"],
        text=fn(e, token),
        occurred_at=e["occurred_at"],
        recorded_at=e["recorded_at"],
        source=e.get("source") or "seed",
        doc_type=doc_type,
        author_role=role,
        consent_id=e.get("consent_id"),
        embed=has_free_text,
    )


# --------------------------------------------------------------------------------------------- rollups
def _day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min, tzinfo=IST)
    return start, start + timedelta(days=1) - timedelta(microseconds=1)


def _daily_text(tok: str, d: date, status: str | None, f: Any) -> str:
    word = _STATUS_WORDS.get(status or "", "") if status else ""
    first = f"Daily summary for {tok}, {d.isoformat()} ({WEEKDAYS[d.weekday()]}): "
    first += f"dose {word}." if word else "no dose report received."
    parts = [first, f"Last 7 days: {f.taken_7d} taken, {f.missed_7d} not taken."]
    if f.quiet_days:
        parts.append(f"No patient report for {f.quiet_days} days.")
    if f.refill_gap_days:
        parts.append(f"Refill is {f.refill_gap_days} days overdue.")
    return " ".join(parts)


def _weekly_text(tok: str, mon: date, sun: date, f: Any) -> str:
    parts = [
        f"Weekly summary for {tok}, {mon.isoformat()} to {sun.isoformat()}: "
        f"{f.taken_7d} doses taken and {f.missed_7d} not taken."
    ]
    if f.top_miss_weekday:
        parts.append(
            f"Most missed doses so far fall on {f.top_miss_weekday} ({f.weekday_misses[f.top_miss_weekday]} times)."
        )
    if f.refill_gap_days:
        parts.append(f"Refill is {f.refill_gap_days} days overdue.")
    if f.quiet_days:
        parts.append(f"No patient report for {f.quiet_days} days.")
    if f.longest_streak:
        parts.append(f"Longest run of doses taken: {f.longest_streak} days.")
    if f.conflicts:
        parts.append("Self-report and the refill record disagree.")
    return " ".join(parts)


def _numbers(f: Any) -> dict[str, Any]:
    n = {k: v for k, v in f.numbers.items() if not k.startswith("window_")}
    return n


def build_rollup_cards(
    events: list[dict[str, Any]], as_of: datetime, token: str, day0: date | None = None
) -> list[RollupCard]:
    """Daily cards for every closed IST day and weekly cards (Mon-Sun) for every closed week up to ``as_of``.

    Each card is computed at its own window close from events recorded by then, so it never changes later
    (late events only appear as event chunks). Numbers come from ``compute_features`` only.
    """
    vis = [e for e in events if e["occurred_at"] <= as_of and e["recorded_at"] <= as_of]
    if not vis:
        return []
    first = _day(min(e["occurred_at"] for e in vis))
    last_closed = _day(as_of) - timedelta(days=1)
    cards: list[RollupCard] = []
    d = first
    while d <= last_closed:
        start, end = _day_bounds(d)
        f = compute_features(vis, end, day0)
        in_win = [e for e in vis if start <= e["occurred_at"] <= end and e["recorded_at"] <= end]
        ck = _checkins([e for e in vis if e["occurred_at"] <= end and e["recorded_at"] <= end])
        status = (ck[d]["payload"].get("status")) if d in ck else None
        ids = sorted(str(e["event_id"]) for e in in_win)
        nums = {**_numbers(f), "day_status": status}
        cards.append(
            RollupCard(
                "daily", _daily_text(token, d, status, f), start, end, nums, ids, dict(f.cites)
            )
        )
        if d.weekday() == 6:  # Sunday closes a week
            mon = d - timedelta(days=6)
            ws, _ = _day_bounds(mon)
            wids = sorted(
                str(e["event_id"])
                for e in vis
                if ws <= e["occurred_at"] <= end and e["recorded_at"] <= end
            )
            cards.append(
                RollupCard(
                    "weekly",
                    _weekly_text(token, mon, d, f),
                    ws,
                    end,
                    _numbers(f),
                    wids,
                    dict(f.cites),
                )
            )
        d += timedelta(days=1)
    return cards
