"""Review contracts: the doctor gate queue, decisions, templates, outbox and Gmail digest/reply.

FROZEN at ``contracts-v1``.

* The queue IS the ``approvals`` table (API name :class:`ReviewItem`).
* ``cm/review/decide.py`` (lane G) is the only decision path (K2). It writes the
  decision, the approval status, the ``ReviewDecisionEvent``, the outbox rows,
  any edit example, the ``resume-{approval_id}`` task row and the audit row in ONE
  transaction.
* ``interrupt_id``: for deep-agent threads it is the HITL tool-call id; for the
  LangGraph review graph it is ``gate:{proposal_group_id}:{redraft_count}`` (T2).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from .domain import Audience, CMModel, EventSource, Lang, OutboundChannel, Tier
from .memory import CitationRef, Sentence, ValidatorReport

# ---------------------------------------------------------------------------
# Enums / aliases
# ---------------------------------------------------------------------------

ReviewKind = Literal[
    "card", "brief", "visit_list", "conflict", "identity", "digest", "needs_human",
    "lab_confirm", "contact_review", "district_report",
]
"""``approvals.kind`` (K1). ``needs_human`` carries ``payload.subkind`` (csv_mapping,
channel_failed, household_declined, ...). A Red system alert is kind ``conflict``, tier ``red``."""

ApprovalStatus = Literal["pending", "approved", "edited", "rejected", "expired", "manual"]
"""``approvals.status``. ``manual`` after 2 re-drafts; the doctor writes the text."""

DecisionAction = Literal["approve", "edit", "reject", "expired"]
"""Internal decision vocabulary; ``expired`` is sweeper-only (K5)."""

PublicDecisionAction = Literal["approve", "edit", "reject"]
"""What the console / Gmail may submit."""

DecisionVia = Literal["console", "gmail", "sweeper"]

DeliveryState = Literal["none", "pending", "sending", "sent", "failed"]
"""Derived from ``outbox.status`` for the approval's rows."""

GraphKind = Literal["deep", "lg"]
SampleReason = Literal["anomaly", "random_10pct"]

OutboxStatus = Literal["pending", "sending", "sent", "failed"]

OutboxKind = Literal[
    # approval-gated (require approval_id + decision_id; DB CHECK)
    "card", "brief", "visit_list", "ai_message", "calendar_event", "district_report", "lab_confirm_notice",
    # system allow-list (require an approved template_id; no approval_id)
    "checkin", "checkin_nudge", "supporter_proxy", "template_prompt", "ack", "danger_ack",
    "red_alert", "escalation_notice", "doctor_digest", "gmail_echo", "consent_echo",
]
"""``outbox.kind``. Mirrors ``cm.outbox_system_kinds()`` in ``0002_reliability.sql``: the
DB-level doctor gate refuses an outbox row without ``approval_id`` unless its kind is a
system kind (all of which must point to an approved template)."""

SYSTEM_OUTBOX_KINDS: frozenset[str] = frozenset({
    "checkin", "checkin_nudge", "supporter_proxy", "template_prompt", "ack", "danger_ack",
    "red_alert", "escalation_notice", "doctor_digest", "gmail_echo", "consent_echo",
})
"""Allow-listed outbox kinds that may exist without an ``approval_id`` (must match the SQL)."""


# ---------------------------------------------------------------------------
# Queue and decisions
# ---------------------------------------------------------------------------


class Recipient(CMModel):
    """Who a send proposal goes to (K3: decide() builds outbox rows from these)."""

    person_id: UUID
    token: str
    channel: OutboundChannel


class EvidenceItem(CMModel):
    """UI shape of ``approvals.evidence`` entries."""

    kind: Literal["driver", "event", "belief", "conflict", "guideline", "risk", "document"]
    label: str = Field(description="e.g. 'Misses Thursdays'")
    value: str | None = Field(default=None, description="e.g. '6 of 8 - posterior 0.97'")
    contribution: float | None = None
    source: EventSource | None = None
    citation: CitationRef


class ProposalOut(CMModel):
    """Typed view of ``approvals.payload``."""

    audience: Audience
    title: str = Field(description="Queue title, e.g. 'Memory card - P-0042 - day 60'")
    channel: OutboundChannel | None = None
    recipients: list[Recipient] = Field(default_factory=list, description="Required for every send artefact (K3)")
    body: str
    sentences: list[Sentence] = Field(default_factory=list)
    template_key: str | None = None
    subkind: str | None = Field(default=None, description="needs_human subkind / conflict rule / visit kind")
    for_date: date | None = None
    data: dict = Field(default_factory=dict, description="Kind-specific structured payload (visit items, identity candidates, ...)")


class ReviewItem(CMModel):
    """API model of an ``approvals`` row."""

    approval_id: UUID
    patient_id: UUID | None = None
    patient_token: str | None = None
    patient_display: str | None = Field(default=None, description="Detokenised for the treating doctor only (audited)")
    thread_id: str
    interrupt_id: str
    task_id: str | None = None
    proposal_group_id: UUID | None = None
    graph_kind: GraphKind
    tier: Tier
    kind: ReviewKind
    title: str
    status: ApprovalStatus
    drivers: list[EvidenceItem] = Field(default_factory=list, max_length=3)
    evidence_count: int = 0
    created_at: datetime
    due_at: datetime = Field(description="Stored: Red created+4h, Amber next 12:00 IST, Green end of day")
    expires_at: datetime
    reminded_at: datetime | None = None
    escalated_at: datetime | None = None
    redraft_count: int = Field(default=0, ge=0, le=2)
    sample_reason: SampleReason | None = Field(default=None, description="Green only")
    delivery: DeliveryState = "none"


class ReviewQueueOut(CMModel):
    """``GET /review/queue`` envelope (P5)."""

    counts: dict[Literal["red", "amber", "green", "overdue", "escalated"], int]
    items: list[ReviewItem]
    next_cursor: str | None = None
    server_time: datetime
    sim_day: int


class DecisionRecord(CMModel):
    """A ``review_decisions`` row for history display."""

    decision_id: UUID
    action: DecisionAction
    doctor_token: str | None = None
    via: DecisionVia
    decided_at: datetime
    reason: str | None = None


class ReviewItemDetail(ReviewItem):
    proposal: ProposalOut
    evidence: list[EvidenceItem] = Field(default_factory=list)
    citations: list[CitationRef] = Field(default_factory=list)
    validator_report: ValidatorReport | None = None
    supporter_preview: ProposalOut | None = None
    history: list[DecisionRecord] = Field(default_factory=list)


class ReviewDecisionIn(CMModel):
    """``POST /review/{approval_id}/decision``. Reject on Red/Amber needs ``reason``."""

    action: PublicDecisionAction
    edited: dict | None = Field(default=None, description="Replaces the proposal args, e.g. {'body': str, 'sentences': [...]} or {'doctor_decision': ...}")
    reason: str | None = Field(default=None, max_length=500)
    evidence_viewed: bool = Field(default=False, description="Audit only")


class ExpiredDecision(CMModel):
    """Sweeper-only decision at 48 h. Nothing is sent."""

    action: Literal["expired"] = "expired"
    reason: str = "expired_48h"


class ReviewDecisionOut(CMModel):
    decision_id: UUID | None = None
    approval_id: UUID
    action: DecisionAction
    status: ApprovalStatus
    via: DecisionVia
    decided_at: datetime | None = None
    resume_task_id: str | None = Field(default=None, description="resume-{approval_id}")
    outbox_ids: list[UUID] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list, description="e.g. doctor-audience number not in cited evidence")
    error_code: Literal["red_not_bulk", "amber_not_viewed", "already_decided", "not_found", "reason_required", "banned_term"] | None = None


class BulkDecisionIn(CMModel):
    """Bulk approve (K4). Red always refused; Amber must be in ``viewed_approval_ids``."""

    approval_ids: list[UUID] = Field(min_length=1, max_length=100)
    action: Literal["approve"] = "approve"
    viewed_approval_ids: list[UUID] = Field(default_factory=list)


class ReviewMetrics(CMModel):
    """P1."""

    days: int
    decided: int
    acceptance_rate: float
    edit_rate: float
    median_minutes_to_decision: dict[Tier, float | None]
    oldest_pending_minutes: float | None = None


# ---------------------------------------------------------------------------
# Templates and outbox
# ---------------------------------------------------------------------------


class Template(CMModel):
    template_id: UUID
    key: str
    lang: Lang
    body: str
    slots: list[str] = Field(default_factory=list)
    tier: Tier
    status: Literal["draft", "approved", "retired"]
    approved_by: str | None = Field(default=None, description="Doctor token")
    approved_at: datetime | None = None


class TemplateDraftIn(CMModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    lang: Lang
    body: str = Field(max_length=600)
    tier: Tier = "green"


class TemplatePreview(CMModel):
    rendered: str
    banned_terms_found: list[str] = Field(default_factory=list, description="Must be empty to approve")
    missing_slots: list[str] = Field(default_factory=list)


class OutboxItem(CMModel):
    """A row of ``outbox``. Only ``cm/router/outbox_drainer.py`` sends it."""

    outbox_id: UUID
    kind: OutboxKind
    recipient_id: UUID
    channel: OutboundChannel
    body: str | None = Field(default=None, description="Purged after 30 days (hash kept)")
    approval_id: UUID | None = None
    decision_id: UUID | None = None
    template_id: UUID | None = None
    status: OutboxStatus
    attempts: int = 0
    next_attempt_at: datetime
    provider_message_id: str | None = None
    sent_at: datetime | None = None
    dedup_key: str = Field(description="{decision_id|template_key}:{recipient_id}:{channel}:{for_date}[:{n}] (C23)")
    for_date: date | None = None
    meta: dict = Field(default_factory=dict, description="Buttons, ForceReply, calendar spec, ...")


class OutboxRef(CMModel):
    """Body of ``/tasks/send``."""

    outbox_id: UUID


class SendResult(CMModel):
    outbox_id: UUID
    status: Literal["sent", "retry", "failed", "skipped"]
    provider_message_id: str | None = None
    skip_reason: Literal["no_consent", "quiet_hours", "banned_term", "rate_limit", "already_sent", "channel_disabled", "invalid_approval"] | None = None
    error: str | None = None
    retry_after_s: float | None = None


# ---------------------------------------------------------------------------
# Digest and Gmail reply
# ---------------------------------------------------------------------------


class DigestItem(CMModel):
    """One numbered line of the Amber/Green digest email (approve-by-reply)."""

    n: int = Field(ge=1)
    approval_id: UUID
    tier: Literal["amber", "green"]
    kind: ReviewKind
    patient_token: str | None = None
    title: str
    summary: str
    due_at: datetime


class ReplyCommand(CMModel):
    verb: Literal["approve", "reject", "edit", "hold"]
    items: list[int] = Field(default_factory=list, description="Digest item numbers; empty = all")
    text: str | None = Field(default=None, description="Reason or replacement text")


class ReplyParse(CMModel):
    commands: list[ReplyCommand]
    parser: Literal["regex", "llm"]
    needs_confirm: bool = False


__all__ = [
    "ReviewKind", "ApprovalStatus", "DecisionAction", "PublicDecisionAction", "DecisionVia", "DeliveryState",
    "GraphKind", "SampleReason", "OutboxStatus", "OutboxKind", "SYSTEM_OUTBOX_KINDS", "Recipient", "EvidenceItem",
    "ProposalOut", "ReviewItem", "ReviewQueueOut", "DecisionRecord", "ReviewItemDetail", "ReviewDecisionIn",
    "ExpiredDecision", "ReviewDecisionOut", "BulkDecisionIn", "ReviewMetrics", "Template", "TemplateDraftIn",
    "TemplatePreview", "OutboxItem", "OutboxRef", "SendResult", "DigestItem", "ReplyCommand", "ReplyParse",
]
