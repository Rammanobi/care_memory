"""Lane F: in-memory fakes for the ports (tests and offline demo)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from cm.channels.ports import Binding


class FakeBindings:
    def __init__(self) -> None:
        self.rows: dict[UUID, Binding] = {}

    def add(self, b: Binding) -> Binding:
        self.rows[b.binding_id] = b
        return b

    def by_chat(self, chat_id: str) -> Binding | None:
        return next((b for b in self.rows.values() if b.external_id == chat_id), None)

    def by_invite(self, code: str) -> Binding | None:
        return next(
            (b for b in self.rows.values() if b.invite_code == code and b.external_id is None), None
        )

    def by_person(self, person_id: UUID, channel: str = "telegram") -> Binding | None:
        return next((b for b in self.rows.values() if b.person_id == person_id), None)

    def activate(self, binding_id: UUID, chat_id: str, at: datetime) -> None:
        b = self.rows[binding_id]
        b.external_id, b.status = chat_id, "active"

    def set_status(self, binding_id: UUID, status: str) -> None:
        self.rows[binding_id].status = status


class FakeEvents:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def append_event(self, event: dict[str, Any]) -> tuple[UUID, bool]:
        for r in self.rows:
            if r["idempotency_key"] == event["idempotency_key"]:
                return r["event_id"], False
        event = {**event, "event_id": uuid4()}
        self.rows.append(event)
        return event["event_id"], True


class FakeConsents:
    def __init__(self) -> None:
        self.state: dict[tuple[UUID, str, str], str] = {}
        self.log: list[tuple[Any, ...]] = []

    def grant(self, person_id: UUID, source: str, purpose: str) -> None:
        self.state[(person_id, source, purpose)] = "granted"

    def has_consent(self, person_id: UUID, source: str, purpose: str, as_of: datetime) -> bool:
        return self.state.get((person_id, source, purpose)) == "granted"

    def record_consent(
        self, person_id: UUID, source: str, purpose: str, state: str, via: str, at: datetime
    ) -> UUID:
        self.state[(person_id, source, purpose)] = state
        self.log.append((person_id, source, purpose, state, via))
        return uuid4()


class FakeOutbox:
    def __init__(self) -> None:
        self.rows: dict[UUID, dict[str, Any]] = {}
        self.sent_keys: set[str] = set()

    def add(self, row: dict[str, Any]) -> dict[str, Any]:
        row.setdefault("outbox_id", uuid4())
        row.setdefault("status", "pending")
        self.rows[row["outbox_id"]] = row
        return row

    def get(self, outbox_id: UUID) -> dict[str, Any] | None:
        return self.rows.get(outbox_id)

    def mark(self, outbox_id: UUID, status: str, **fields: Any) -> None:
        r = self.rows[outbox_id]
        r["status"] = status
        r.update(fields)
        if status == "sent" and r.get("dedup_key"):
            self.sent_keys.add(r["dedup_key"])

    def already_sent(self, dedup_key: str) -> bool:
        return dedup_key in self.sent_keys

    def sent_today(self, recipient_id: UUID, day: date) -> int:
        return sum(
            1
            for r in self.rows.values()
            if r["status"] == "sent" and r["recipient_id"] == recipient_id
        )


class FakeTasks:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []

    def enqueue(self, queue: str, name: str, payload: Any) -> None:
        self.calls.append((queue, name, payload))


class FakeFastPath:
    def __init__(self) -> None:
        self.missed: list[UUID] = []
        self.red: list[UUID] = []

    def missed_dose(self, patient_id: UUID, event: dict[str, Any]) -> None:
        self.missed.append(patient_id)

    def red_symptom(self, patient_id: UUID, event: dict[str, Any]) -> None:
        self.red.append(patient_id)


class FakeAudit:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def audit(self, action: str, **fields: Any) -> None:
        self.rows.append((action, fields))
