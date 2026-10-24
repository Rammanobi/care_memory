"""Cross-lane service Protocols (``typing.Protocol``, ``runtime_checkable``).

FROZEN at ``contracts-v1``. Each owning lane ships a real implementation and an
in-memory fake in its ``fakes.py`` so other lanes can build against fakes.

| Protocol           | Owner | Implementation module                     |
|--------------------|-------|-------------------------------------------|
| EventStore         | A     | cm/store/events_repo.py + as_of.py        |
| ConsentReader      | A     | cm/store/consent.py                       |
| Clock              | A     | cm/core/clock.py                          |
| TaskQueue          | A     | cm/core/tasks.py                          |
| TaskRunsRepo       | A     | cm/store/task_runs_repo.py                |
| ApprovalsRepo      | A     | cm/store/approvals_repo.py                |
| OutboxRepo         | A     | cm/store/outbox_repo.py                   |
| SettingsRepo       | A     | cm/store/settings_repo.py                 |
| HouseholdRepo      | A     | cm/store/household_repo.py                |
| ModelFactory       | A     | cm/core/llm.py                            |
| MemoryEngine       | C     | cm/memory/pipeline.py, snapshot.py        |
| Reconciler         | D     | cm/rules/reconcile.py, fast_path.py       |
| Validator          | D     | cm/validator/cite_or_cut.py               |
| IdentityResolver   | D     | cm/identity/resolver.py                   |
| ReviewService      | G     | cm/review/decide.py                       |
| TelegramClient     | F     | cm/channels/telegram.py                   |
| GmailClient        | M     | cm/channels/gmail.py                      |
| CalendarClient     | M     | cm/channels/calendar.py                   |
| Router             | F     | cm/router/router.py, outbox_drainer.py    |

Signatures here are the contract; argument names are binding.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable
from uuid import UUID

from .admin import RuleThresholds
from .agents import ErrorClass, IdentityMatch, IdentityQuery, TaskState
from .api import CalendarEventSpec, HouseholdContactIn, HouseholdContactOut
from .domain import ConsentSource, ConsentStateValue, Event, OutboundChannel, Patient, Purpose
from .evalsim import TaskRunStatus
from .memory import Conflict, EvidenceBundle, MemorySnapshot, RiskScore, Sentence, ValidatorReport
from .review import (
    ExpiredDecision,
    OutboxItem,
    ReviewDecisionIn,
    ReviewDecisionOut,
    ReviewItem,
    SendResult,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps contracts importable without pandas
    import pandas as pd

ModelRole = Literal["ORCHESTRATOR", "WORKER", "VISION", "EMBEDDING", "JUDGE"]


# ---------------------------------------------------------------------------
# Lane A: data core
# ---------------------------------------------------------------------------


@runtime_checkable
class EventStore(Protocol):
    def append(self, event: Event) -> tuple[UUID, bool]:
        """Idempotent insert on ``idempotency_key``. Returns (event_id, created). Drops events without active consent."""
        ...

    def bulk_append(self, events: Sequence[Event]) -> int:
        """Seed path. Returns rows inserted."""
        ...

    def query(self, patient_id: UUID, as_of: datetime, *, types: Sequence[str] | None = None,
              since: datetime | None = None) -> list[Event]:
        """``occurred_at <= as_of AND recorded_at <= as_of``, latest non-superseded, withdrawn sources dropped (M2)."""
        ...

    def query_frame(self, patient_ids: Sequence[UUID] | None, as_of: datetime) -> pd.DataFrame:
        """Same predicate as :meth:`query`, returned as a DataFrame for the engine."""
        ...

    def get(self, event_id: UUID) -> Event | None: ...


@runtime_checkable
class ConsentReader(Protocol):
    def is_active(self, person_id: UUID, source: ConsentSource, purpose: Purpose, at: datetime) -> bool: ...

    def latest(self, person_id: UUID) -> dict[tuple[str, str], ConsentStateValue]:
        """Latest state per (source, purpose)."""
        ...

    def withdrawn_sources(self, person_id: UUID, at: datetime) -> set[str]: ...

    def frame(self, person_ids: Sequence[UUID] | None = None) -> pd.DataFrame: ...


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Timezone-aware; maps wall time onto the sim day in demo mode. Never use datetime.now()."""
        ...

    def today(self) -> date: ...

    def sim_day(self) -> int: ...

    def day_to_date(self, day: int) -> date: ...


@runtime_checkable
class TaskQueue(Protocol):
    def enqueue(self, queue: Literal["agent-runs", "resumes", "outbound"], path: str, body: dict[str, Any], *,
                task_id: str, schedule_time: datetime | None = None) -> bool:
        """Named Cloud Task (``task_id`` = name, colon-free). Returns False if the name already exists."""
        ...


@runtime_checkable
class TaskRunsRepo(Protocol):
    def create(self, task_id: str, task_type: str, *, thread_id: str | None = None,
               patient_id: UUID | None = None) -> bool:
        """INSERT ... ON CONFLICT (task_id) DO NOTHING. Returns created."""
        ...

    def claim(self, task_id: str, worker_instance: str, attempt: int) -> TaskRunStatus | None:
        """queued|retrying -> running; None if already running/done (duplicate delivery)."""
        ...

    def heartbeat(self, task_id: str, *, progress: float | None = None, step: str | None = None) -> None: ...

    def set_state(self, task_id: str, state: TaskState, *, error: str | None = None,
                  error_class: ErrorClass | None = None) -> None: ...

    def add_usage(self, task_id: str, tokens_in: int, tokens_out: int, cost_usd: float) -> None: ...

    def get(self, task_id: str) -> TaskRunStatus | None: ...

    def stale_running(self, older_than_s: int) -> list[TaskRunStatus]: ...


@runtime_checkable
class ApprovalsRepo(Protocol):
    def upsert(self, *, thread_id: str, interrupt_id: str, graph_kind: Literal["deep", "lg"], kind: str, tier: str,
               payload: dict[str, Any], evidence: list[dict[str, Any]], patient_id: UUID | None, task_id: str | None,
               proposal_group_id: UUID | None = None, redraft_count: int = 0,
               sample_reason: str | None = None) -> UUID:
        """Idempotent on (thread_id, interrupt_id); computes due_at / expires_at. Returns approval_id."""
        ...

    def get(self, approval_id: UUID) -> ReviewItem | None: ...

    def queue(self, *, doctor_id: UUID | None = None, tier: str | None = None, status: str = "pending",
              kind: str | None = None, patient_id: UUID | None = None, cursor: str | None = None,
              limit: int = 50) -> tuple[list[ReviewItem], str | None]: ...

    def due_for_escalation(self, now: datetime) -> list[ReviewItem]: ...

    def mark_reminded(self, approval_id: UUID, at: datetime) -> None: ...

    def mark_escalated(self, approval_id: UUID, at: datetime) -> None: ...


@runtime_checkable
class OutboxRepo(Protocol):
    def upsert(self, item: OutboxItem) -> tuple[UUID, bool]:
        """Idempotent on dedup_key. Returns (outbox_id, created)."""
        ...

    def claim(self, worker: str, *, channel: OutboundChannel | None = None, limit: int = 20) -> list[OutboxItem]:
        """``status='pending' AND next_attempt_at <= now() FOR UPDATE SKIP LOCKED`` -> sending."""
        ...

    def mark_sent(self, outbox_id: UUID, provider_message_id: str | None, sent_at: datetime) -> None: ...

    def mark_retry(self, outbox_id: UUID, next_attempt_at: datetime, error: str) -> None: ...

    def mark_failed(self, outbox_id: UUID, error: str) -> None: ...

    def release_stuck(self, older_than_s: int = 300) -> int: ...

    def get(self, outbox_id: UUID) -> OutboxItem | None: ...


@runtime_checkable
class SettingsRepo(Protocol):
    def thresholds(self) -> RuleThresholds:
        """60 s cache."""
        ...

    def channel_enabled(self, channel: str) -> bool: ...

    def get(self, key: str) -> tuple[Any, int] | None:
        """(value, version)."""
        ...

    def put(self, key: str, value: Any, *, expected_version: int, updated_by: UUID) -> int:
        """Optimistic lock; raises on version mismatch. Returns the new version."""
        ...


@runtime_checkable
class HouseholdRepo(Protocol):
    def apply(self, contact: HouseholdContactIn, *, actor_id: UUID) -> HouseholdContactOut:
        """Append HouseholdContactEvent(s) then update the projection (encrypting name under the patient DEK)."""
        ...

    def list(self, patient_id: UUID, *, decrypt_names: bool) -> list[HouseholdContactOut]: ...

    def rebuild(self, patient_id: UUID) -> int:
        """Rebuild the projection from events."""
        ...


@runtime_checkable
class ModelFactory(Protocol):
    def get_model(self, role: ModelRole) -> Any:
        """A LangChain chat model (or embeddings for EMBEDDING) built with ``init_chat_model``; OpenAI/DeepSeek only."""
        ...


# ---------------------------------------------------------------------------
# Lane C / D: engine, rules, validator, identity
# ---------------------------------------------------------------------------


@runtime_checkable
class MemoryEngine(Protocol):
    def run_in_memory(self, events: pd.DataFrame, consents: pd.DataFrame, as_of_days: list[int], *,
                      exclude_sources: Sequence[str] = ()) -> Any:
        """M1. Pure, DB-free; returns ``InMemoryResult`` (frozen dataclass: .risk, .beliefs). No truth parameter."""
        ...

    def snapshot(self, patient_id: UUID, day: int, exclude_sources: Sequence[str] = ()) -> MemorySnapshot: ...

    def risk(self, patient_id: UUID, as_of: date) -> RiskScore | None: ...

    def evidence_bundle(self, patient_id: UUID, as_of: date) -> EvidenceBundle: ...

    def run_nightly_patient(self, patient_id: UUID, as_of: date) -> dict[str, Any]: ...


@runtime_checkable
class Reconciler(Protocol):
    def reconcile_frame(self, events: pd.DataFrame, patient: Patient, as_of: date,
                        thresholds: RuleThresholds) -> list[Conflict]:
        """M3. Pure; R1-R6."""
        ...

    def reconcile(self, patient_id: UUID, as_of: date) -> list[Conflict]: ...

    def fast_path(self, event: Event) -> list[Conflict]:
        """R2 / R4 only, on ingest."""
        ...


@runtime_checkable
class Validator(Protocol):
    def validate(self, sentences: list[Sentence], bundle: EvidenceBundle, *,
                 audience: Literal["doctor", "supporter", "patient", "sts"]) -> tuple[list[Sentence], ValidatorReport]: ...

    def banned_terms(self, text: str, lang: str = "en") -> list[str]: ...

    def check_numbers(self, text: str, refs: list[str], bundle: EvidenceBundle) -> list[str]: ...


@runtime_checkable
class IdentityResolver(Protocol):
    def resolve(self, query: IdentityQuery) -> IdentityMatch: ...


# ---------------------------------------------------------------------------
# Lane G: review service (the only decision path)
# ---------------------------------------------------------------------------


@runtime_checkable
class ReviewService(Protocol):
    def decide(self, approval_id: UUID, d: ReviewDecisionIn | ExpiredDecision, *,
               via: Literal["console", "gmail", "sweeper"], actor_id: UUID | None) -> ReviewDecisionOut:
        """K2: one transaction; 409 already_decided; Red cannot be decided via gmail."""
        ...


# ---------------------------------------------------------------------------
# Lane F / M: channels and router
# ---------------------------------------------------------------------------


@runtime_checkable
class TelegramClient(Protocol):
    def send_message(self, chat_id: str, text: str, *, buttons: list[list[dict[str, str]]] | None = None,
                     force_reply: bool = False, protect_content: bool = True) -> str:
        """Returns provider message id. Raises a retryable error with retry_after on 429."""
        ...

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None: ...


@runtime_checkable
class GmailClient(Protocol):
    def send(self, to: str, subject: str, body_text: str, *, reply_to: str | None = None,
             thread_id: str | None = None) -> str: ...

    def history_list(self, mailbox: str, start_history_id: int) -> list[dict[str, Any]]: ...

    def get_message(self, mailbox: str, message_id: str) -> dict[str, Any]: ...

    def watch(self, mailbox: str, topic: str) -> dict[str, Any]: ...


@runtime_checkable
class CalendarClient(Protocol):
    def upsert_event(self, calendar_id: str, spec: CalendarEventSpec, *, event_id: str | None = None) -> str: ...

    def patch_color(self, calendar_id: str, event_id: str, color_id: str) -> None: ...


@runtime_checkable
class Router(Protocol):
    def deliver(self, outbox_id: UUID) -> SendResult:
        """Checks in order: approval/template valid, consent, quiet hours, banned terms, rate limit, dedup."""
        ...

    def drain(self, channel: OutboundChannel | None = None, limit: int = 20) -> list[SendResult]: ...


__all__ = [
    "ModelRole", "EventStore", "ConsentReader", "Clock", "TaskQueue", "TaskRunsRepo", "ApprovalsRepo", "OutboxRepo",
    "SettingsRepo", "HouseholdRepo", "ModelFactory", "MemoryEngine", "Reconciler", "Validator", "IdentityResolver",
    "ReviewService", "TelegramClient", "GmailClient", "CalendarClient", "Router",
]
