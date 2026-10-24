"""Lane D: LLM-free ingest fast path (arch P8). Runs R2 and R4 only, for one new event.

Called from the ``append_event()`` post-commit hook. Pure: the caller passes the patient's
regimen context (prior events) when it has it; without context R2 assumes first-line and
fails safe (raises the Red). Errors must never block an append: the hook catches them and
the nightly reconcile catches up.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from cm.contracts.admin import RuleThresholds
from cm.contracts.memory import Conflict

from . import rules_r2, rules_r4
from ._common import prepare, to_ev

FAST_TYPES = frozenset({"LabResult", "SymptomReport"})


def fast_path(
    event: Any,
    context: Iterable[Any] = (),
    patient: Any = None,
    thresholds: RuleThresholds | None = None,
) -> list[Conflict]:
    """R2/R4 check for one event (+ optional prior events). ``[]`` for any other event type."""
    ev = to_ev(event)
    if ev is None or ev.type not in FAST_TYPES:
        return []
    pat = patient or {"patient_id": ev.patient_id, "treatment_start": ev.occurred}
    ctx = prepare([*context, event], pat, ev.recorded, thresholds)
    mine = next((e for e in ctx.events if e.event_id == ev.event_id), None)
    if mine is None:  # superseded or not visible
        return []
    hit = (
        rules_r2.check_lab(ctx, mine)
        if mine.type == "LabResult"
        else rules_r4.check_report(ctx, mine)
    )
    return [hit] if hit is not None else []
