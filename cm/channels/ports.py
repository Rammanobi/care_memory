"""Lane F: Protocols the Telegram lane depends on. The real store and queue implement these.

Method names mirror cm/store/* and cm.core.tasks. The integrator writes thin adapters
(see cm/channels/NOTES.md). Events are plain dicts using the field names of
cm.store.events_repo.NewEvent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass
class Binding:
    binding_id: UUID
    person_id: UUID
    role: str  # patient | supporter | ...
    patient_id: UUID | None = None
    external_id: str | None = None  # chat id once bound
    invite_code: str | None = None
    invite_expires_at: datetime | None = None
    status: str = "pending"  # pending | active | blocked | revoked
    lang: str = "en"


class BindingPort(Protocol):
    def by_chat(self, chat_id: str) -> Binding | None: ...
    def by_invite(self, code: str) -> Binding | None: ...
    def by_person(self, person_id: UUID, channel: str = "telegram") -> Binding | None: ...
    def activate(self, binding_id: UUID, chat_id: str, at: datetime) -> None: ...
    def set_status(self, binding_id: UUID, status: str) -> None: ...


class EventPort(Protocol):
    def append_event(self, event: dict[str, Any]) -> tuple[UUID, bool]:
        """Insert, ON CONFLICT (idempotency_key) DO NOTHING. Returns (event_id, inserted)."""


class ConsentPort(Protocol):
    def has_consent(self, person_id: UUID, source: str, purpose: str, as_of: datetime) -> bool: ...
    def record_consent(
        self, person_id: UUID, source: str, purpose: str, state: str, via: str, at: datetime
    ) -> UUID: ...


class OutboxPort(Protocol):
    def get(self, outbox_id: UUID) -> dict[str, Any] | None: ...
    def mark(self, outbox_id: UUID, status: str, **fields: Any) -> None: ...
    def already_sent(self, dedup_key: str) -> bool: ...
    def sent_today(self, recipient_id: UUID, day: date) -> int: ...


class TaskPort(Protocol):
    def enqueue(self, queue: str, name: str, payload: Any) -> None:
        """Same signature as cm.core.tasks.enqueue."""


class FastPathPort(Protocol):
    """Plain-rules hand-off, no LLM."""

    def missed_dose(self, patient_id: UUID, event: dict[str, Any]) -> None: ...
    def red_symptom(self, patient_id: UUID, event: dict[str, Any]) -> None: ...


class MessagePort(Protocol):
    """Free-text chat messages: stored as an event plus a doctor-visible request; ack rate limit."""

    def save(
        self,
        b: Binding,
        update_id: int,
        text: str,
        category: str,
        at: datetime,
        *,
        chat_id: int | None = None,
        message_id: int | None = None,
    ) -> tuple[bool, UUID | None]:
        """Idempotent per update_id. Returns (newly_stored, request_id or None when a repeat was folded)."""

    def claim_ack(self, person_id: UUID, urgent: bool, at: datetime, window_s: int) -> bool:
        """True (and records it) when no ack of this kind went to this person in the last window_s."""

    def first_name(self, person_id: UUID) -> str | None: ...


class AuditPort(Protocol):
    def audit(self, action: str, **fields: Any) -> None: ...


class TelegramClient(Protocol):
    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        reply_to_message_id: int | None = None,
    ) -> str:
        """``reply_to_message_id`` threads the message under an earlier one. Returns the provider message id. Raises TgRetryAfter, TgAuthError, TgBlocked, TgTransient."""

    async def edit_reply_markup(
        self, chat_id: str, message_id: str, reply_markup: dict[str, Any] | None
    ) -> None: ...
