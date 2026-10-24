"""Lane F: bind a Telegram chat to a person with a one-time invite code; revoke on /stop."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from cm.channels.ports import AuditPort, Binding, BindingPort, ConsentPort

UNBOUND_TEXT = "This service is by invitation from your clinic."
STOPPED_TEXT = "You've turned off these messages. Type /start to turn them back on."
BOUND_TEXT = "You are connected. Thank you."
BAD_CODE_TEXT = "That code is not valid. Please ask your clinic for a new one."

PURPOSES_PATIENT = ("daily_checkin", "care_coordination")


@dataclass
class BindResult:
    ok: bool
    text: str
    binding: Binding | None = None


def chat_hash(chat_id: str) -> str:
    return hashlib.sha256(chat_id.encode()).hexdigest()[:16]


def bind_telegram(
    code: str,
    chat_id: str,
    *,
    bindings: BindingPort,
    consents: ConsentPort,
    audit: AuditPort,
    now: datetime,
) -> BindResult:
    """/start <code>: single-use, expiring. Records telegram consent for the person on success."""
    code = (code or "").strip()
    b = bindings.by_invite(code) if code else None
    if b is None or (b.invite_expires_at is not None and b.invite_expires_at <= now):
        audit.audit("tg_bind_rejected", chat=chat_hash(chat_id))
        return BindResult(False, BAD_CODE_TEXT if code else UNBOUND_TEXT)
    bindings.activate(b.binding_id, chat_id, now)
    b.external_id, b.status = chat_id, "active"
    purposes = PURPOSES_PATIENT if b.role == "patient" else ("care_coordination",)
    for p in purposes:
        consents.record_consent(b.person_id, "telegram", p, "granted", "telegram", now)
    audit.audit("tg_bound", person_id=str(b.person_id), chat=chat_hash(chat_id))
    return BindResult(True, BOUND_TEXT, b)


def stop_telegram(
    chat_id: str, *, bindings: BindingPort, consents: ConsentPort, audit: AuditPort, now: datetime
) -> BindResult:
    """/stop: withdraw every telegram purpose and revoke the binding."""
    b = bindings.by_chat(chat_id)
    if b is None:
        return BindResult(False, UNBOUND_TEXT)
    for p in PURPOSES_PATIENT:
        consents.record_consent(b.person_id, "telegram", p, "withdrawn", "telegram", now)
    bindings.set_status(b.binding_id, "revoked")
    b.status = "revoked"
    audit.audit("tg_stopped", person_id=str(b.person_id), chat=chat_hash(chat_id))
    return BindResult(True, STOPPED_TEXT, b)
