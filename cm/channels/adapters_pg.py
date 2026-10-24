"""Integration: Postgres adapters for the lane-F Protocols in ports.py, plus factory helpers.

Every method is a thin wrapper over cm.store.*; no SQL here. ``Binding.binding_id`` is the person_id.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from cm.channels.ports import Binding
from cm.channels.tg_inbound import Deps
from cm.channels.tg_ratelimit import ChatLimiter
from cm.core import clock, db, tasks
from cm.core.logging import get_logger
from cm.store import approvals_repo, channels_repo, consent, events_repo, outbox_repo

log = get_logger()


def _binding(r: dict[str, Any] | None) -> Binding | None:
    if r is None:
        return None
    return Binding(
        binding_id=r["person_id"],
        person_id=r["person_id"],
        role=r["role"],
        patient_id=r["patient_id"],
        external_id=r["external_id"],
        invite_code=r["invite_code"],
        invite_expires_at=r["invite_expires_at"],
        status=r["status"],
        lang=r["lang"],
    )


class PgBindings:
    def by_chat(self, chat_id: str) -> Binding | None:
        return _binding(channels_repo.binding_by_chat(chat_id))

    def by_invite(self, code: str) -> Binding | None:
        return _binding(channels_repo.binding_by_invite(code))

    def by_person(self, person_id: UUID, channel: str = "telegram") -> Binding | None:
        return _binding(channels_repo.binding_by_person(person_id))

    def activate(self, binding_id: UUID, chat_id: str, at: datetime) -> None:
        channels_repo.activate_binding(binding_id, chat_id, at)

    def set_status(self, binding_id: UUID, status: str) -> None:
        channels_repo.set_binding_status(binding_id, status)


class PgEvents:
    """Adds the authorising consent_id that every non-system event must carry."""

    def append_event(self, event: dict[str, Any]) -> tuple[UUID, bool]:
        ev = dict(event)
        with db.transaction() as conn:
            if ev.get("source") not in ("system", "console") and not ev.get("consent_id"):
                person = ev.get("reporter_id") or channels_repo.patient_person(
                    ev["patient_id"], conn=conn
                )
                ev["consent_id"] = consent.latest_consent_id(
                    person, ev["source"], ev["recorded_at"], conn=conn
                )
            return events_repo.append_event(events_repo.NewEvent(**ev), conn=conn)


class PgConsents:
    def has_consent(self, person_id: UUID, source: str, purpose: str, as_of: datetime) -> bool:
        return consent.consent_state(person_id, as_of).get(source, {}).get(purpose) == "granted"

    def record_consent(
        self, person_id: UUID, source: str, purpose: str, state: str, via: str, at: datetime
    ) -> UUID:
        return consent.record_consent(person_id, source, purpose, state, at, via)


class PgOutbox:
    def get(self, outbox_id: UUID) -> dict[str, Any] | None:
        return outbox_repo.get(outbox_id)

    def mark(self, outbox_id: UUID, status: str, **fields: Any) -> None:
        outbox_repo.mark(outbox_id, status, **fields)

    def already_sent(self, dedup_key: str) -> bool:
        return outbox_repo.already_sent(dedup_key)

    def sent_today(self, recipient_id: UUID, day: date) -> int:
        return outbox_repo.sent_today(recipient_id, day)


class PgAudit:
    def audit(self, action: str, **fields: Any) -> None:
        try:
            channels_repo.write_audit(action, fields, clock.now())
        except Exception as exc:  # audit must never break the webhook ack
            log.warning("audit write failed", action=action, error=type(exc).__name__)


class PgTasks:
    def enqueue(self, queue: str, name: str, payload: Any) -> None:
        tasks.enqueue(queue, name, payload)


# ---- fast path: plain rules, no LLM ---------------------------------------------------------
MISSED_BODY = (
    "We noticed you have missed a few doses. Please call your clinic today so we can help. "
    "Your care team will also get in touch."
)
RED_BODY = (
    "You told us about symptoms that need attention. Please contact your clinic now or go to the "
    "nearest health centre. Your care team has been told."
)


class PgFastPath:
    def __init__(self, threshold: int | None = None, window_days: int = 3) -> None:
        self.threshold = threshold or int(os.environ.get("FASTPATH_MISSED_THRESHOLD", "3"))
        self.window = window_days

    def missed_dose(self, patient_id: UUID, event: dict[str, Any]) -> None:
        at = event["recorded_at"]
        n = events_repo.missed_days(patient_id, at - timedelta(days=self.window), at)
        if n >= self.threshold:
            self._draft(patient_id, at, "missed_dose", "Missed doses: " + str(n) + " days", MISSED_BODY)

    def red_symptom(self, patient_id: UUID, event: dict[str, Any]) -> None:
        self._draft(patient_id, event["recorded_at"], "red_symptom", "Danger symptom reported", RED_BODY)

    def _draft(self, patient_id: UUID, at: datetime, rule: str, title: str, body: str) -> UUID | None:
        person = channels_repo.patient_person(patient_id)
        if person is None:
            return None
        day = at.astimezone(clock.IST).date().isoformat()
        payload = {
            "audience": "patient",
            "title": title,
            "channel": "telegram",
            "body": body,
            "recipients": [{"person_id": str(person), "token": "", "channel": "telegram"}],
            "subkind": f"fastpath_{rule}",
            "data": {"rule": rule, "source": "fast_path"},
        }
        return approvals_repo.upsert(
            {
                "approval_id": uuid4(),
                "patient_id": patient_id,
                "thread_id": f"fast-{rule}-{patient_id}-{day}",
                "interrupt_id": "fastpath",
                "tier": "red",
                "kind": "conflict",
                "payload": payload,
                "created_at": at,
                "due_at": at + timedelta(hours=4),
                "expires_at": at + timedelta(hours=48),
            }
        )


def build_deps(secret: str | None = None) -> Deps:
    """Inbound deps for POST /webhooks/telegram. The secret is read from the environment per call."""
    return Deps(
        secret=secret if secret is not None else os.environ.get("TELEGRAM_WEBHOOK_SECRET", ""),
        bindings=PgBindings(),
        events=PgEvents(),
        consents=PgConsents(),
        outbox=PgOutbox(),
        tasks=PgTasks(),
        fast=PgFastPath(),
        audit=PgAudit(),
        now=clock.now,
    )


_limiter: ChatLimiter | None = None


def shared_limiter() -> ChatLimiter:
    global _limiter
    if _limiter is None:
        import time

        from cm.channels.telegram import limiter_from_env

        _limiter = limiter_from_env(time.monotonic)
    return _limiter
