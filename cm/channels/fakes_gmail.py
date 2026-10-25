"""In-memory fakes for lane M tests and offline demo."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from cm.channels.ports_gmail import CursorLostError
from cm.contracts.review import ReviewDecisionIn, ReviewDecisionOut


class FakeGmailClient:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.messages: dict[str, dict[str, Any]] = {}
        self.attachments: dict[tuple[str, str], bytes] = {}  # (message_id, attachment_id) -> bytes
        self.history: list[tuple[int, str]] = []  # (historyId, message_id)
        self.latest = 100
        self.cursor_floor = 0
        self.errors: list[Exception] = []  # popped one per API call
        self.calls: list[str] = []
        self.get_count = 0

    def _maybe_fail(self, name: str) -> None:
        self.calls.append(name)
        if self.errors:
            raise self.errors.pop(0)

    def add_inbound(self, message: dict[str, Any]) -> int:
        self.latest += 1
        self.messages[message["id"]] = message
        self.history.append((self.latest, message["id"]))
        return self.latest

    def send(self, **kw: Any) -> str:
        self._maybe_fail("send")
        self.sent.append(kw)
        return f"sent-{len(self.sent)}"

    def history_list(self, start_history_id: int) -> tuple[list[str], int]:
        self._maybe_fail("history_list")
        if start_history_id < self.cursor_floor:
            raise CursorLostError()
        return [m for h, m in self.history if h > start_history_id], self.latest

    def list_recent(self, query: str) -> list[str]:
        self._maybe_fail("list_recent")
        return list(self.messages)

    def profile_history_id(self) -> int:
        return self.latest

    def get_message(self, message_id: str) -> dict[str, Any]:
        self._maybe_fail("get_message")
        self.get_count += 1
        return self.messages[message_id]

    def fetch_attachment(self, message_id: str, attachment_id: str) -> bytes:
        self._maybe_fail("fetch_attachment")
        return self.attachments[(message_id, attachment_id)]

    def watch(self, topic: str) -> dict[str, Any]:
        self._maybe_fail("watch")
        return {"historyId": self.latest, "expiration": 9_999_999_999_000}


class FakeQueue:
    def __init__(self) -> None:
        self.tasks: dict[str, dict[str, Any]] = {}

    def enqueue(self, task_id: str, payload: dict[str, Any]) -> bool:
        if task_id in self.tasks:
            return False
        self.tasks[task_id] = payload
        return True


class FakeState:
    def __init__(self) -> None:
        self.cursor: int | None = None
        self.done: set[str] = set()
        self.expiry: int | None = None

    def get_cursor(self) -> int | None:
        return self.cursor

    def advance_cursor(self, history_id: int) -> int:
        self.cursor = max(self.cursor or 0, history_id)
        return self.cursor

    def is_processed(self, message_id: str) -> bool:
        return message_id in self.done

    def mark_processed(self, message_id: str) -> None:
        self.done.add(message_id)

    def get_watch_expiry(self) -> int | None:
        return self.expiry

    def set_watch(self, history_id: int, expiration_ms: int) -> None:
        self.expiry = expiration_ms
        self.advance_cursor(history_id)


class FakeTokens:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def mint(self, rows: list[tuple[str, UUID]], doctor_id: str, expires_at: datetime) -> None:
        for h, a in rows:
            self.rows[h] = {"approval": a, "doctor": doctor_id, "exp": expires_at, "used": False}

    def consume(self, token_hash: str, doctor_id: str, now: datetime):
        r = self.rows.get(token_hash)
        if r is None:
            return "unknown", None
        if r["doctor"] != doctor_id:
            return "wrong_doctor", None
        if r["used"]:
            return "used", None
        if r["exp"] <= now:
            return "expired", None
        r["used"] = True
        return "ok", r["approval"]

    def release(self, token_hash: str) -> None:
        if token_hash in self.rows:
            self.rows[token_hash]["used"] = False


class FakeDecide:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, ReviewDecisionIn, str, str]] = []
        self.already: set[UUID] = set()

    def __call__(self, approval_id: UUID, body: ReviewDecisionIn, *, via: str, actor: str) -> ReviewDecisionOut:
        self.calls.append((approval_id, body, via, actor))
        if approval_id in self.already:
            return ReviewDecisionOut(approval_id=approval_id, action=body.action, status="approved",
                                     via="console", error_code="already_decided")
        return ReviewDecisionOut(approval_id=approval_id, action=body.action, status="approved",
                                 via="gmail", decision_id=uuid4())


class FakeOutboxWriter:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def enqueue_echo(self, **kw: Any) -> None:
        self.rows.setdefault(kw["dedup_key"], kw)


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def record(self, event: str, **fields: Any) -> None:
        self.events.append((event, fields))


class FakeCalendarClient:
    def __init__(self) -> None:
        self.events: dict[str, dict[str, Any]] = {}
        self.upserts = 0

    def upsert_event(self, calendar_id: str, event_id: str, body: dict[str, Any]) -> str:
        self.upserts += 1
        self.events[event_id] = body
        return event_id


class FakeConsentStore:
    def __init__(self) -> None:
        self.rows: list[tuple] = []

    def append(self, person_id, source, purpose, state, via, effective_at) -> None:
        self.rows.append((person_id, source, purpose, state, via, effective_at))

    def latest(self, person_id, source, purpose):
        for r in reversed(self.rows):
            if r[:3] == (person_id, source, purpose):
                return r[3]
        return None
