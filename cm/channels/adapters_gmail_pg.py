"""Integration: Postgres adapters for the lane-M Protocols (TokenStore, GmailStateStore, DecideFn).

Thin wrappers over cm.store.gmail_repo and cm.review.decide; no SQL here. Doctor decisions go only through
``cm.review.decide.decide`` (non-negotiable 14). cm.review / psycopg are imported lazily so this module
imports without a database.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from cm.contracts.review import ReviewDecisionIn, ReviewDecisionOut
from cm.core import clock
from cm.store import gmail_repo


class PgTokenStore:
    """approval_tokens. ``doctor_id`` is the doctor's person_id (uuid string)."""

    def mint(self, rows: list[tuple[str, UUID]], doctor_id: str, expires_at: datetime) -> None:
        gmail_repo.mint_tokens(rows, UUID(str(doctor_id)), expires_at)

    def consume(self, token_hash: str, doctor_id: str, now: datetime) -> tuple[str, UUID | None]:
        return gmail_repo.consume_token(token_hash, UUID(str(doctor_id)), now)

    def release(self, token_hash: str) -> None:
        gmail_repo.release_token(token_hash)


class PgGmailState:
    """cm.gmail_state keyed by mailbox; message dedup via audit_log."""

    def __init__(self, mailbox: str, now: Callable[[], datetime] = clock.now) -> None:
        self.mailbox, self._now = mailbox, now

    def get_cursor(self) -> int | None:
        return gmail_repo.get_cursor(self.mailbox)

    def advance_cursor(self, history_id: int) -> int:
        return gmail_repo.advance_cursor(self.mailbox, history_id)

    def is_processed(self, message_id: str) -> bool:
        return gmail_repo.is_processed(message_id, self._now())

    def mark_processed(self, message_id: str) -> None:
        gmail_repo.mark_processed(message_id, self._now())

    def get_watch_expiry(self) -> int | None:
        return gmail_repo.get_watch_expiry_ms(self.mailbox)

    def set_watch(self, history_id: int, expiration_ms: int) -> None:
        gmail_repo.set_watch(self.mailbox, history_id, expiration_ms)


class PgDecide:
    """DecideFn over cm.review.decide.decide. Business-rule failures become ``error_code`` results."""

    def __init__(self, decide_fn: Callable[..., ReviewDecisionOut] | None = None) -> None:
        self._decide = decide_fn

    def __call__(self, approval_id: UUID, body: ReviewDecisionIn, *, via: str, actor: str) -> ReviewDecisionOut:
        from cm.review import decide as dec

        fn = self._decide or dec.decide
        try:
            return fn(approval_id, body, via=via, actor_id=UUID(str(actor)))
        except dec.DecisionError as exc:
            code: Any = exc.code if exc.code in (
                "red_not_bulk", "amber_not_viewed", "already_decided", "not_found", "reason_required", "banned_term"
            ) else None
            if code is None:
                raise
            status = "approved" if code == "already_decided" else "pending"
            return ReviewDecisionOut(approval_id=approval_id, action=body.action, status=status,
                                     via="console" if code == "already_decided" else "gmail", error_code=code)
