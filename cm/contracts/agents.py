"""Agent contracts: task envelopes, tool context, intake/identity, investigation, Q&A, judge and guards.

FROZEN at ``contracts-v1``.

Id formats (C21):
* ``task_id`` is colon-free and doubles as the Cloud Task name:
  ``{task_type}-{token|all}-d{day}-{hash8}``, ``resume-{approval_id}``, ``send-{outbox_id}``,
  ``nudge-{outbox_id}``, ``drain-{channel}-{epoch_min}``, ``nightly-{token}-d{day}``,
  ``tg-{update_id}``, ``gm-{gmail_message_id}``, ``gmail-fetch-{historyId}``, ``{task_id}-a{n}`` (sweeper).
* ``thread_id`` keeps colons: ``{task_type}:{token}:{day}:{uuid8}`` (< 255 chars).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from .domain import BeliefKind, CMModel, Purpose, Role

TASK_ID_PATTERN = r"^[A-Za-z0-9_-]{1,500}$"
"""Cloud Tasks names allow letters, digits, hyphens and underscores only (no colons)."""

TaskType = Literal["ingest_event", "nightly_patient", "investigate", "prepare_visit_list", "doctor_digest", "consent_change"]
"""Orchestrated task types. ``dashboard_question`` was removed (P8: ``/query`` runs inline)."""

TaskState = Literal["queued", "running", "waiting_human", "retrying", "succeeded", "failed"]
"""``task_runs.state`` (T10: the column is ``state``, not ``status``)."""

ErrorClass = Literal["retryable", "spend_cap", "auth", "invalid", "unknown"]
"""``task_runs.error_class``. ``spend_cap`` and ``auth`` are never retried."""

TaskRunType = Literal[
    "ingest_event", "nightly_patient", "investigate", "prepare_visit_list", "doctor_digest", "consent_change",
    "resume", "send", "drain_outbox", "checkins", "checkin_nudge", "digest", "visit_lists", "gmail_fetch",
    "gmail_watch_renew", "gmail_sweep", "portal_sync", "calendar_sync", "district_report", "nightly", "seed",
    "eval", "sweep", "migrate",
]
"""``task_runs.task_type``: orchestrated task types plus deterministic worker/job kinds."""


class Actor(CMModel):
    """Who caused a task: a person (by id/role/token) or the system."""

    kind: Literal["person", "system"]
    person_id: UUID | None = None
    role: Role | None = None
    token: str | None = None


class TaskEnvelope(CMModel):
    """The unit of agent work, enqueued on ``agent-runs`` and posted to ``/tasks/run``."""

    task_id: str = Field(pattern=TASK_ID_PATTERN, description="Colon-free; = Cloud Task name; = task_runs.task_id")
    task_type: TaskType
    thread_id: str = Field(max_length=254, description="{task_type}:{token}:{day}:{uuid8}")
    patient_id: UUID | None = None
    patient_token: str | None = None
    actor: Actor
    as_of_day: int = Field(ge=0, description="Sim day the task reasons as of")
    payload: dict[str, Any] = Field(default_factory=dict, description="Task-specific: RawInbound for ingest_event, {question} for investigate, ...")
    idempotency_key: str = Field(max_length=255)
    created_at: datetime | None = None


class Todo(CMModel):
    content: str
    status: Literal["pending", "in_progress", "completed"]


class TaskResult(CMModel):
    status: Literal["done", "interrupted", "failed", "partial"]
    review_item_ids: list[UUID] = Field(default_factory=list, description="approval_ids created")
    artifacts: dict[str, Any] = Field(default_factory=dict)
    todos: list[Todo] = Field(default_factory=list)
    error: str | None = None


class HitlDecision(CMModel):
    """One decision passed to ``Command(resume={"decisions": [...]})``, in pending-action order."""

    type: Literal["approve", "edit", "reject", "expired"]
    edited_action: dict[str, Any] | None = Field(default=None, description="{'name': tool, 'args': {...}} for edit")
    message: str | None = Field(default=None, description="Reject reason fed back for re-draft")


class ResumeEnvelope(CMModel):
    """Body of ``/tasks/resume`` (task id ``resume-{approval_id}``)."""

    task_id: str = Field(pattern=TASK_ID_PATTERN)
    thread_id: str
    approval_id: UUID
    graph_kind: Literal["deep", "lg"]
    decisions: list[HitlDecision] = Field(min_length=1)


class ToolContext(CMModel):
    """Passed as ``config['configurable']['ctx']``; every governed tool authorises against it."""

    task_id: str
    task_type: TaskType
    thread_id: str
    actor_role: Role | Literal["system"]
    actor_id: UUID | None = None
    patient_id: UUID | None = None
    patient_token: str | None = None
    patient_scope: list[UUID] | None = Field(default=None, description="None = single patient_id only")
    purpose: Purpose
    as_of: date
    as_of_day: int


class AgentTaskIn(CMModel):
    """``POST /agent/tasks`` (P1: investigate)."""

    task_type: Literal["investigate"] = "investigate"
    patient_id: UUID
    question: str = Field(min_length=3, max_length=500)


class TaskAccepted(CMModel):
    task_id: str
    thread_id: str | None = None


class TaskStatus(CMModel):
    """``GET /agent/tasks/{task_id}``; todos come from the checkpoint state."""

    task_id: str
    status: TaskState
    todos: list[Todo] = Field(default_factory=list)
    result: TaskResult | None = None
    review_item_ids: list[UUID] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Intake and identity
# ---------------------------------------------------------------------------


class Attachment(CMModel):
    gcs_uri: str
    mime_type: str
    sha256: str
    size_bytes: int = Field(ge=0)


class RawInbound(CMModel):
    """Raw input for ``ingest_event`` (free text, unknown CSV headers, lab files)."""

    channel: Literal["telegram", "web", "gmail", "csv", "lab_upload", "supporter"]
    external_id: str = Field(description="update_id, gmail message id, upload id ...")
    patient_id: UUID | None = None
    reporter_id: UUID | None = None
    text: str | None = Field(default=None, description="Tokenised before any LLM sees it; wrapped as <untrusted>")
    callback_data: str | None = None
    attachment: Attachment | None = None
    received_ts: datetime = Field(description="Becomes events.recorded_at")


class ParsedEvent(CMModel):
    """An event the intake agent proposes; ``append_event`` validates it into a full domain Event."""

    type: Literal["DoseCheckin", "SymptomReport", "WeightReport", "PaymentReport", "ContextNote"]
    occurred_at: datetime | None = None
    payload: dict[str, Any]


class ParsedInbound(CMModel):
    """Intake output. Never infers 'taken' from ambiguous text; < 0.7 confidence -> needs_clarification."""

    events: list[ParsedEvent] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    needs_clarification: bool = False
    danger_keywords: list[str] = Field(default_factory=list, description="Deterministic pre-scan hits (R4 fast-path)")


class IdentityQuery(CMModel):
    name: str | None = Field(default=None, description="Never sent to an LLM untokenised")
    phone_last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    dob: date | None = None
    nikshay_id: str | None = None
    lab_id: str | None = None
    source: Literal["chemist", "lab", "portal"]
    source_ref: str | None = None


class IdentityCandidate(CMModel):
    patient_id: UUID
    token: str
    score: float = Field(ge=0, le=100)


class IdentityMatch(CMModel):
    """phone + name >= 90 -> auto; 75-90 -> review (Amber identity item); < 75 -> none. The LLM never sets patient_id."""

    patient_id: UUID | None = None
    score: float = Field(ge=0, le=100)
    band: Literal["auto", "review", "none"]
    candidates: list[IdentityCandidate] = Field(default_factory=list)
    explanation: str | None = Field(default=None, description="P1 one-line LLM explanation (review band only)")


# ---------------------------------------------------------------------------
# Investigation
# ---------------------------------------------------------------------------


class InvestigationRequest(CMModel):
    patient_id: UUID
    as_of: date
    question: str


class Finding(CMModel):
    """Must reference >= 1 belief or event id returned by a tool in this thread (checked post-hoc)."""

    claim: str
    stat: str | None = None
    belief_ids: list[UUID] = Field(default_factory=list)
    event_ids: list[UUID] = Field(default_factory=list)


class HypothesisRequest(CMModel):
    """Investigator proposal tested by nightly detectors (row of ``hypothesis_requests``)."""

    kind: BeliefKind
    params: dict[str, Any] = Field(default_factory=dict)
    rationale: str | None = None


class InvestigationReport(CMModel):
    findings: list[Finding] = Field(default_factory=list)
    hypotheses_to_test: list[HypothesisRequest] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dashboard Q&A (P1, inline in cm-api)
# ---------------------------------------------------------------------------


class QueryIn(CMModel):
    question: str = Field(min_length=3, max_length=500)
    scope: Literal["clinic", "district", "block"] | None = Field(default=None, description="Narrowed to the JWT scope server-side")
    block_id: UUID | None = None
    day: int | None = Field(default=None, description="Defaults to sim_clock")


class ToolCallUsed(CMModel):
    n: int = Field(description="Citation number [n]")
    tool: str
    args: dict[str, Any]
    row_count: int
    result_preview: list[dict[str, Any]] = Field(default_factory=list)


class AnswerTable(CMModel):
    columns: list[str]
    rows: list[list[str | int | float | None]] = Field(description="None = suppressed (<5)")


class QueryAnswer(CMModel):
    answer_text: str = Field(description="Contains [n] markers")
    table: AnswerTable | None = None
    tool_calls_used: list[ToolCallUsed] = Field(default_factory=list)
    as_of: date
    suppressed_cells: int = 0
    numbers_verified: bool
    refused: bool = False
    refusal_reason: str | None = None
    latency_ms: int


# ---------------------------------------------------------------------------
# Judge and guards
# ---------------------------------------------------------------------------


class JudgeVerdict(CMModel):
    """``cm-eval`` LLM judge result (never in the live 20 s path)."""

    faithful: bool
    unsupported_claims: list[str] = Field(default_factory=list)
    score: int = Field(ge=1, le=5)


class TokenMap(CMModel):
    """In-memory map from placeholder token to original value for one prompt. NEVER persisted or logged."""

    tokens: dict[str, str] = Field(default_factory=dict, description="'[PHONE_1]' -> original")
    kinds: dict[str, Literal["person", "phone", "email", "address", "id"]] = Field(default_factory=dict)


class InjectionScan(CMModel):
    suspected: bool
    patterns: list[str] = Field(default_factory=list)


__all__ = [
    "TASK_ID_PATTERN", "TaskType", "TaskState", "ErrorClass", "TaskRunType", "Actor", "TaskEnvelope", "Todo",
    "TaskResult", "HitlDecision", "ResumeEnvelope", "ToolContext", "AgentTaskIn", "TaskAccepted", "TaskStatus",
    "Attachment", "RawInbound", "ParsedEvent", "ParsedInbound", "IdentityQuery", "IdentityCandidate",
    "IdentityMatch", "InvestigationRequest", "Finding", "HypothesisRequest", "InvestigationReport", "QueryIn",
    "ToolCallUsed", "AnswerTable", "QueryAnswer", "JudgeVerdict", "TokenMap", "InjectionScan",
]
