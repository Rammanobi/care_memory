"""Lane D: shared helpers for the R1-R6 reconciler (pure, deterministic, no I/O, no LLM).

Every rule works on :class:`Ev`, a normalised, as-of-filtered view of L0 events.
Inputs may be a pandas DataFrame (``cm.events`` rows, payload either flattened or in a
``payload`` column), a list of dicts, or a list of contract ``Event`` models.

Date semantics: all dates are IST calendar dates (``cm.core.clock.ist_date``). An event is
visible at ``as_of`` when ``occurred <= as_of`` and ``recorded <= as_of`` (bitemporal, M2).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid5

from cm.contracts.admin import RuleThresholds
from cm.contracts.domain import EVENT_ENVELOPE_FIELDS
from cm.contracts.memory import CitationRef, Conflict
from cm.core.clock import ist_date

CONFLICT_NS = UUID("8b4e2f61-3c0d-5a7e-9f12-6d5c4b3a2e10")
"""Namespace for ``conflict_id = uuid5(NS, f"{pid}|{rule}|{anchor}")`` (02 F6). Never change it."""

MAX_EVIDENCE = 20
"""Evidence lists are capped (first 20 + count in the title), per 02 F6."""

_LABELS = {
    "DoseCheckin": "Dose report",
    "SymptomReport": "Symptom report",
    "SupporterVisit": "Supporter visit",
    "PillCount": "Pill count",
    "Dispense": "Chemist dispense",
    "LabResult": "Lab result",
    "PaymentReport": "Payment report",
    "PortalPayment": "Portal payment",
    "PortalRegistration": "Portal registration",
    "ContextNote": "Context note",
    "CheckinPrompt": "Check-in prompt",
    "RegimenChange": "Regimen record",
    "HouseholdContactEvent": "Household contact",
}


@dataclass(frozen=True)
class Ev:
    """One visible event: envelope essentials plus its type-specific payload ``p``."""

    event_id: str
    patient_id: str
    type: str
    occurred: date
    recorded: date
    reporter_mode: str
    source: str
    supersedes: str | None
    p: Mapping[str, Any] = field(default_factory=dict, hash=False, compare=False)

    def get(self, key: str, default: Any = None) -> Any:
        return self.p.get(key, default)


@dataclass(frozen=True)
class Ctx:
    """Everything a rule needs, prepared once by :func:`prepare`."""

    patient_id: str
    treatment_start: date
    as_of: date
    thresholds: RuleThresholds
    events: tuple[Ev, ...]

    def of_type(self, *types: str) -> list[Ev]:
        return [e for e in self.events if e.type in types]

    def day(self, d: date) -> int:
        """Treatment day of a calendar date (day 0 = treatment start)."""
        return (d - self.treatment_start).days


# ---------------------------------------------------------------------------
# Value coercion
# ---------------------------------------------------------------------------


def to_date(v: Any) -> date | None:
    """Coerce a datetime / date / ISO string / pandas Timestamp to an IST date."""
    if v is None or (isinstance(v, float) and v != v):  # NaN from pandas
        return None
    if hasattr(v, "to_pydatetime"):
        v = v.to_pydatetime()
    if isinstance(v, datetime):
        return ist_date(v) if v.tzinfo else v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        s = v.strip()
        if len(s) == 10:
            return date.fromisoformat(s)
        return to_date(datetime.fromisoformat(s.replace("Z", "+00:00")))
    raise TypeError(f"not a date: {type(v).__name__}")


def pdate(e: Ev, key: str) -> date | None:
    """A payload date field (``for_date``, ``visit_date``, ``paid_on`` ...) as a date; None if absent/bad."""
    try:
        return to_date(e.get(key))
    except (TypeError, ValueError):
        return None


def _row_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "model_dump"):
        return row.model_dump(mode="python")
    if isinstance(row, Mapping):
        out = dict(row)
    else:
        raise TypeError(f"unsupported event row: {type(row).__name__}")
    payload = out.pop("payload", None)
    if isinstance(payload, Mapping):
        out = {**payload, **out}
    return out


def to_ev(row: Any) -> Ev | None:
    """Normalise one row; ``None`` for rows that carry no usable envelope."""
    d = _row_dict(row)
    occurred, recorded = to_date(d.get("occurred_at")), to_date(d.get("recorded_at"))
    if occurred is None or recorded is None or not d.get("type"):
        return None
    sup = d.get("supersedes")
    return Ev(
        event_id=str(d.get("event_id")),
        patient_id=str(d.get("patient_id")),
        type=str(d["type"]),
        occurred=occurred,
        recorded=recorded,
        reporter_mode=str(d.get("reporter_mode") or ""),
        source=str(d.get("source") or ""),
        supersedes=str(sup) if sup else None,
        p={k: v for k, v in d.items() if k not in EVENT_ENVELOPE_FIELDS},
    )


def iter_rows(events: Any) -> Iterable[Any]:
    if events is None:
        return []
    if hasattr(events, "to_dict") and hasattr(events, "columns"):  # pandas DataFrame
        return events.to_dict(orient="records")
    return events


# ---------------------------------------------------------------------------
# Preparation
# ---------------------------------------------------------------------------


def _patient_fields(patient: Any) -> tuple[str, date]:
    if isinstance(patient, Mapping):
        pid, start = patient.get("patient_id"), patient.get("treatment_start")
    else:
        pid, start = getattr(patient, "patient_id", None), getattr(patient, "treatment_start", None)
    start_d = to_date(start)
    if pid is None or start_d is None:
        raise ValueError("patient needs patient_id and treatment_start")
    return str(pid), start_d


def visible(evs: Iterable[Ev], patient_id: str, as_of: date) -> tuple[Ev, ...]:
    """As-of filter + this patient only + drop tombstones and superseded events. Sorted, deterministic."""
    seen = [
        e
        for e in evs
        if e.patient_id == patient_id
        and e.occurred <= as_of
        and e.recorded <= as_of
        and e.type != "Tombstone"
    ]
    superseded = {e.supersedes for e in seen if e.supersedes}
    kept = [e for e in seen if e.event_id not in superseded]
    uniq = {e.event_id: e for e in kept}  # duplicate rows collapse on event_id
    return tuple(sorted(uniq.values(), key=lambda e: (e.occurred, e.recorded, e.type, e.event_id)))


def prepare(events: Any, patient: Any, as_of: date, thresholds: RuleThresholds | None) -> Ctx:
    """Build a :class:`Ctx`. Idempotent: a ``Ctx`` passed as ``events`` is returned as is."""
    if isinstance(events, Ctx):
        return events
    pid, start = _patient_fields(patient)
    evs = [ev for ev in (to_ev(r) for r in iter_rows(events)) if ev is not None]
    return Ctx(pid, start, as_of, thresholds or RuleThresholds(), visible(evs, pid, as_of))


# ---------------------------------------------------------------------------
# Conflict construction
# ---------------------------------------------------------------------------


def conflict_id(patient_id: str, rule: str, anchor: str) -> UUID:
    return uuid5(CONFLICT_NS, f"{patient_id}|{rule}|{anchor}")


def cite(ctx: Ctx, e: Ev) -> CitationRef:
    day = ctx.day(e.occurred)
    return CitationRef(
        ref_type="E", ref_id=e.event_id, label=f"{_LABELS.get(e.type, e.type)} d{day}", sim_day=day
    )


def make_conflict(
    ctx: Ctx,
    *,
    rule: str,
    tier: str,
    anchor: str,
    title: str,
    evidence: Iterable[Ev],
    opened: date,
    closed: date | None = None,
) -> Conflict:
    """A Conflict with E refs (deduped, order kept, capped at :data:`MAX_EVIDENCE`)."""
    uniq: dict[str, Ev] = {}
    for e in evidence:
        uniq.setdefault(e.event_id, e)
    refs = [cite(ctx, e) for e in list(uniq.values())[:MAX_EVIDENCE]]
    return Conflict(
        conflict_id=conflict_id(ctx.patient_id, rule, anchor),
        patient_id=UUID(ctx.patient_id),
        rule=rule,
        tier=tier,
        title=title,
        evidence_ids=[r.ref for r in refs],
        evidence=refs,
        opened_as_of=opened,
        closed_as_of=closed,
    )


def days(start: date, end: date) -> Iterable[date]:
    """Inclusive calendar range."""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)
