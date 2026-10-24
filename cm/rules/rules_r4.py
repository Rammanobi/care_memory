"""Lane D: R4 red-flag symptom (Red). 02 F6, arch §3.4.

Any danger symptom in a ``SymptomReport``: the ``danger`` flag set at intake, a danger code
(blood in cough, breathlessness, chest pain, yellow eyes, confusion, persistent high fever),
or a danger checklist index (5 yellow eyes, 6 blood when coughing, 7 hard to breathe; the
Telegram checklist order). One conflict per report; it stays open until a doctor acts.
Also runs on the ingest fast path.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from cm.contracts.admin import RuleThresholds
from cm.contracts.memory import Conflict

from ._common import Ctx, Ev, make_conflict, prepare

RULE = "R4"
DANGER_CODES: dict[str, str] = {
    "cough_blood": "blood when coughing",
    "breathless": "hard to breathe",
    "chest_pain": "chest pain",
    "yellow_eyes": "yellow eyes or skin",
    "confusion": "confusion",
    "high_fever_persistent": "persistent high fever",
}
DANGER_INDEXES: dict[int, str] = {
    5: "yellow eyes or skin",
    6: "blood when coughing",
    7: "hard to breathe",
}


def danger_labels(e: Ev) -> list[str]:
    """Plain-language danger labels found in a report (sorted, deduped). Empty = not a danger report."""
    labels = {DANGER_CODES[c] for c in (e.get("codes") or []) if c in DANGER_CODES}
    for i in e.get("items") or []:
        if isinstance(i, int) and not isinstance(i, bool) and i in DANGER_INDEXES:
            labels.add(DANGER_INDEXES[i])
    if not labels and e.get("danger") is True:
        labels.add("danger sign")
    return sorted(labels)


def check_report(ctx: Ctx, e: Ev) -> Conflict | None:
    if e.type != "SymptomReport":
        return None
    labels = danger_labels(e)
    if not labels:
        return None
    title = f"Danger symptom reported on day {ctx.day(e.occurred)}: {', '.join(labels)}."
    return make_conflict(
        ctx, rule=RULE, tier="red", anchor=e.event_id, title=title, evidence=[e], opened=e.recorded
    )


def evaluate(
    events: Any, patient: Any, as_of: date, thresholds: RuleThresholds | None = None
) -> list[Conflict]:
    """Rule R4."""
    ctx = prepare(events, patient, as_of, thresholds)
    out = [check_report(ctx, e) for e in ctx.of_type("SymptomReport")]
    return [c for c in out if c is not None]
