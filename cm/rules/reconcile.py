"""Lane D: the reconciler (M3). One implementation of R1-R6; pure and deterministic.

``reconcile_frame(events, patient, as_of, thresholds)`` is what the evaluator and nightly call.
``reconcile(pid, as_of)`` = load (``cm.store`` read path) + ``reconcile_frame``.
Numbers in conflict titles come only from these rules, never from an LLM.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from cm.contracts.admin import RuleThresholds
from cm.contracts.memory import Conflict
from cm.core.clock import IST

from . import rules_r1, rules_r2, rules_r3, rules_r4, rules_r5, rules_r6
from ._common import prepare, to_date, to_ev

RULES: tuple[tuple[str, Callable[..., list[Conflict]]], ...] = (
    ("R1", rules_r1.evaluate),
    ("R2", rules_r2.evaluate),
    ("R3", rules_r3.evaluate),
    ("R4", rules_r4.evaluate),
    ("R5", rules_r5.evaluate),
    ("R6", rules_r6.evaluate),
)


def _order(c: Conflict) -> tuple[Any, ...]:
    return (c.opened_as_of, c.rule, str(c.conflict_id))


def reconcile_frame(
    events: Any,
    patient: Any,
    as_of: date,
    thresholds: RuleThresholds | None = None,
) -> list[Conflict]:
    """Pure reconcile over a DataFrame (or list of rows/events). Open and closed conflicts known at ``as_of``."""
    ctx = prepare(events, patient, as_of, thresholds)
    out: dict[UUID, Conflict] = {}
    for _rule, fn in RULES:
        for c in fn(ctx, None, as_of):
            out[c.conflict_id] = c
    return sorted(out.values(), key=_order)


def open_conflicts(conflicts: Iterable[Conflict], as_of: date) -> list[Conflict]:
    return [c for c in conflicts if c.closed_as_of is None or c.closed_as_of > as_of]


def merge_upsert(
    stored: Iterable[Conflict], fresh: Iterable[Conflict], as_of: date
) -> list[Conflict]:
    """Upsert semantics for the ``conflicts`` table (pure).

    Keeps the earliest ``opened_as_of``; takes the fresh tier, title, evidence and closure.
    A stored open conflict that the rules no longer produce is closed at ``as_of``.
    """
    prev = {c.conflict_id: c for c in stored}
    out: dict[UUID, Conflict] = {}
    for c in fresh:
        old = prev.get(c.conflict_id)
        opened = min(old.opened_as_of, c.opened_as_of) if old else c.opened_as_of
        out[c.conflict_id] = c.model_copy(update={"opened_as_of": opened})
    for cid, old in prev.items():
        if cid not in out:
            out[cid] = (
                old
                if old.closed_as_of is not None
                else old.model_copy(update={"closed_as_of": as_of})
            )
    return sorted(out.values(), key=_order)


# ---------------------------------------------------------------------------
# Loader (the only impure part; injectable for tests)
# ---------------------------------------------------------------------------


def _default_events(pid: UUID, as_of: date) -> list[dict[str, Any]]:
    from cm.store import events_repo  # lazy: keeps the rules importable without a DB driver

    return events_repo.query(pid, datetime.combine(as_of, time.max, tzinfo=IST))


def _default_thresholds() -> RuleThresholds:
    from cm.store import settings_repo

    row = settings_repo.get_setting("thresholds")
    return RuleThresholds.model_validate(row["value"]) if row else RuleThresholds()


def patient_from_events(pid: UUID, rows: Iterable[Any]) -> dict[str, Any]:
    """Minimal patient context: treatment start from RegimenChange, else PortalRegistration, else first event."""
    evs = sorted(
        (e for e in (to_ev(r) for r in rows) if e is not None),
        key=lambda e: (e.occurred, e.event_id),
    )
    for kind, key in (
        ("RegimenChange", "effective_date"),
        ("PortalRegistration", "treatment_start"),
    ):
        hit = [e for e in evs if e.type == kind]
        if hit:
            return {
                "patient_id": pid,
                "treatment_start": to_date(hit[0].get(key)) or hit[0].occurred,
            }
    if not evs:
        raise LookupError(f"no events for patient {pid}")
    return {"patient_id": pid, "treatment_start": evs[0].occurred}


def reconcile(
    pid: UUID,
    as_of: date,
    *,
    patient: Any = None,
    thresholds: RuleThresholds | None = None,
    load_events: Callable[[UUID, date], list[Any]] | None = None,
) -> list[Conflict]:
    """Load one patient's events as of ``as_of`` and reconcile them."""
    rows = (load_events or _default_events)(pid, as_of)
    pat = patient if patient is not None else patient_from_events(pid, rows)
    return reconcile_frame(rows, pat, as_of, thresholds or _default_thresholds())
