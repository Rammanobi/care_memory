"""Lane D: turn conflicts into approval *drafts* (M8). Drafts only: nothing here sends.

A draft is the deterministic system text the review graph (``cm/agents/gate.py``) stores as one
``approvals(kind="conflict")`` row, deduped on ``conflict_id``. It is doctor-facing, has no
channel and no recipients, so it cannot become an outbox row without a doctor decision
through ``cm/review/decide.py``. Every sentence cites the conflict (``C:``) and its evidence
(``E:``); memory-engine conflicts are handled the same way. No LLM is involved.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from cm.contracts.memory import CitationRef, Conflict, Sentence
from cm.contracts.review import ProposalOut

RULE_LABELS: dict[str, str] = {
    "R1": "Refill gap while self-reporting taken",
    "R2": "Resistance result vs regimen",
    "R3": "Payment mismatch",
    "R4": "Danger symptom",
    "R5": "Non-response streak",
    "R6": "Contacts not screened",
}


@dataclass(frozen=True)
class ApprovalDraft:
    """What the review graph needs to create one pending conflict approval."""

    dedupe_key: str
    kind: str
    tier: str
    patient_id: str
    conflict_id: str
    proposal: ProposalOut
    evidence: tuple[CitationRef, ...]


def conflict_ref(c: Conflict) -> str:
    return f"C:{c.conflict_id}"


def draft_for_conflict(c: Conflict, *, patient_token: str | None = None) -> ApprovalDraft:
    label = RULE_LABELS.get(c.rule, c.rule)
    who = f" - {patient_token}" if patient_token else ""
    refs = [conflict_ref(c), *c.evidence_ids]
    proposal = ProposalOut(
        audience="doctor",
        title=f"{c.rule} {label}{who}",
        channel=None,
        recipients=[],
        body=c.title,
        sentences=[Sentence(text=c.title, refs=refs)],
        template_key=None,
        subkind=c.rule,
        data={
            "conflict_id": str(c.conflict_id),
            "rule": c.rule,
            "tier": c.tier,
            "evidence_ids": list(c.evidence_ids),
            "opened_as_of": c.opened_as_of.isoformat(),
        },
    )
    return ApprovalDraft(
        dedupe_key=f"conflict:{c.conflict_id}",
        kind="conflict",
        tier=c.tier,
        patient_id=str(c.patient_id),
        conflict_id=str(c.conflict_id),
        proposal=proposal,
        evidence=tuple(c.evidence),
    )


def drafts_for_opened(
    previous: Iterable[Conflict], current: Iterable[Conflict], as_of: date
) -> list[ApprovalDraft]:
    """One draft per conflict that is open at ``as_of`` and was not already known (dedupe on conflict_id)."""
    seen = {c.conflict_id for c in previous}
    out = [
        draft_for_conflict(c)
        for c in current
        if c.conflict_id not in seen and (c.closed_as_of is None or c.closed_as_of > as_of)
    ]
    uniq = {d.dedupe_key: d for d in out}
    return sorted(uniq.values(), key=lambda d: (d.tier != "red", d.dedupe_key))
