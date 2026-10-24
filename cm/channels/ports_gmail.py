"""Lane M ports: Protocols and errors for Gmail, Calendar and consent. No network here."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import UUID

from cm.contracts.review import ReviewDecisionIn, ReviewDecisionOut

# Gmail quota units (RELIABILITY_PLAYBOOK).
UNITS = {"messages.send": 100, "messages.get": 20, "history.list": 2, "users.watch": 100}

BANNED_RE = re.compile(
    r"\bTB\b|tubercul|isoniazid|rifampi[cn]|pyrazinamide|ethambutol|streptomycin|bedaquiline|linezolid|\bHRZE\b",
    re.IGNORECASE,
)


def has_banned_term(text: str) -> bool:
    return bool(BANNED_RE.search(text))


class GmailQuotaError(Exception):
    """429 / rateLimitExceeded. Retryable after ``retry_after`` seconds."""

    def __init__(self, retry_after: float | None = None) -> None:
        super().__init__("gmail quota")
        self.retry_after = retry_after


class GmailTransientError(Exception):
    """5xx or timeout. Retryable."""


class GmailAuthError(Exception):
    """invalid_grant / 401 / 403. Never retried; surfaces a console banner."""


class CursorLostError(Exception):
    """history.list 404: the saved historyId is too old."""


@runtime_checkable
class GmailApi(Protocol):
    def send(self, *, to: str, subject: str, body_text: str, body_html: str | None = None,
             reply_to: str | None = None, thread_id: str | None = None,
             in_reply_to: str | None = None, message_id: str | None = None) -> str: ...

    def history_list(self, start_history_id: int) -> tuple[list[str], int]:
        """Return (new message ids, latest historyId). Raise CursorLostError on 404."""
        ...

    def list_recent(self, query: str) -> list[str]: ...

    def profile_history_id(self) -> int: ...

    def get_message(self, message_id: str) -> dict[str, Any]: ...

    def watch(self, topic: str) -> dict[str, Any]:
        """Return {historyId: int, expiration: epoch_ms}."""
        ...


@runtime_checkable
class TaskQueue(Protocol):
    def enqueue(self, task_id: str, payload: dict[str, Any]) -> bool:
        """Named task. False when the name already exists (ALREADY_EXISTS)."""
        ...


@runtime_checkable
class GmailStateStore(Protocol):
    def get_cursor(self) -> int | None: ...

    def advance_cursor(self, history_id: int) -> int:
        """GREATEST(old, new); returns the stored value."""
        ...

    def is_processed(self, message_id: str) -> bool: ...

    def mark_processed(self, message_id: str) -> None: ...

    def get_watch_expiry(self) -> int | None: ...

    def set_watch(self, history_id: int, expiration_ms: int) -> None: ...


TokenStatus = Literal["ok", "used", "expired", "unknown", "wrong_doctor"]


@runtime_checkable
class TokenStore(Protocol):
    """approval_tokens. token_hash = sha256(T + ':' + n)."""

    def consume(self, token_hash: str, doctor_id: str, now: datetime) -> tuple[TokenStatus, UUID | None]:
        """Atomic: mark used only if unused, unexpired and owned by doctor_id."""
        ...

    def release(self, token_hash: str) -> None:
        """Undo a consume when decide() failed before deciding."""
        ...

    def mint(self, rows: list[tuple[str, UUID]], doctor_id: str, expires_at: datetime) -> None: ...


@runtime_checkable
class DecideFn(Protocol):
    """Adapter over cm.review.decide.decide (same function the console uses)."""

    def __call__(self, approval_id: UUID, body: ReviewDecisionIn, *, via: str, actor: str) -> ReviewDecisionOut: ...


@runtime_checkable
class OutboxWriter(Protocol):
    def enqueue_echo(self, *, dedup_key: str, to: str, subject: str, body_text: str,
                     thread_id: str | None, in_reply_to: str | None) -> None:
        """Template gmail_echo row (approved template, no decision needed)."""
        ...


@runtime_checkable
class AuditLog(Protocol):
    def record(self, event: str, **fields: Any) -> None: ...


@runtime_checkable
class CalendarApi(Protocol):
    def upsert_event(self, calendar_id: str, event_id: str, body: dict[str, Any]) -> str: ...


@runtime_checkable
class ConsentStore(Protocol):
    def append(self, person_id: UUID, source: str, purpose: str, state: str, via: str,
               effective_at: datetime) -> None: ...

    def latest(self, person_id: UUID, source: str, purpose: str) -> str | None:
        """granted | withdrawn | None (never)."""
        ...
