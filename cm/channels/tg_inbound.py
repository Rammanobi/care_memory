"""Lane F: inbound Telegram handler. Plain Python, no LLM, no LangChain.

Order for a tap: verify secret, dedupe, check binding + consent, SAVE EVENT, enqueue tg-{update_id},
fast path, then build the (inline) reply. Always returns (status, body) quickly.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from cm.channels import tg_callback as cb
from cm.channels import tg_text
from cm.channels.binding import (
    STOPPED_TEXT,
    UNBOUND_TEXT,
    bind_telegram,
    chat_hash,
    stop_telegram,
)
from cm.channels.ports import (
    AuditPort,
    Binding,
    BindingPort,
    ConsentPort,
    EventPort,
    FastPathPort,
    MessagePort,
    OutboxPort,
    TaskPort,
)
from cm.contracts.api import TelegramUpdate
from cm.core import clock

NOTED = "Noted"
OK: dict[str, Any] = {"ok": True}
LATE_AFTER_S = 2 * 3600


@dataclass
class Deps:
    secret: str
    bindings: BindingPort
    events: EventPort
    consents: ConsentPort
    outbox: OutboxPort
    tasks: TaskPort
    fast: FastPathPort
    audit: AuditPort
    now: Callable[[], datetime]
    messages: MessagePort | None = None  # None: legacy enqueue-only behaviour (supporters, old tests)


def verify_secret(header: str | None, expected: str) -> bool:
    if not header or not expected:
        return False
    return hmac.compare_digest(header.encode(), expected.encode())


def _say(chat_id: str, text: str) -> dict[str, Any]:
    return {"method": "sendMessage", "chat_id": chat_id, "text": text}


def handle_update(
    raw: dict[str, Any], header_secret: str | None, d: Deps
) -> tuple[int, dict[str, Any]]:
    """Entry point for POST /webhooks/telegram. Returns (http_status, json_body)."""
    if not verify_secret(header_secret, d.secret):
        d.audit.audit("tg_bad_secret")
        return 401, {"ok": False}
    try:
        upd = TelegramUpdate.model_validate(raw)
    except Exception:
        return 200, OK
    if upd.callback_query:
        return 200, _on_callback(upd, d)
    if upd.message:
        return 200, _on_message(upd, d)
    return 200, OK


def _on_message(upd: TelegramUpdate, d: Deps) -> dict[str, Any]:
    m = upd.message or {}
    chat = m.get("chat") or {}
    if chat.get("type") != "private":
        return OK
    chat_id = str(chat.get("id"))
    text = (m.get("text") or "").strip()
    now = d.now()
    low = text.lower()  # phone keyboards capitalise: "/Stop" must still stop
    if low.startswith("/start"):
        r = bind_telegram(
            text[6:].strip(),
            chat_id,
            bindings=d.bindings,
            consents=d.consents,
            audit=d.audit,
            now=now,
        )
        return _say(chat_id, r.text)
    if low.startswith("/stop"):
        return _say(
            chat_id,
            stop_telegram(
                chat_id, bindings=d.bindings, consents=d.consents, audit=d.audit, now=now
            ).text,
        )
    b = d.bindings.by_chat(chat_id)
    if b is None:
        d.audit.audit("tg_unbound_message", chat=chat_hash(chat_id))
        return _say(chat_id, UNBOUND_TEXT)
    if b.status != "active" or not d.consents.has_consent(
        b.person_id, "telegram", "daily_checkin", now
    ):
        return _say(chat_id, STOPPED_TEXT)
    if d.messages is not None and b.role == "patient" and b.patient_id is not None:
        return _free_text(upd, text, b, chat_id, now, d)
    d.tasks.enqueue(
        "agent-runs",
        f"tg-{upd.update_id}",
        {
            "kind": "ingest_event",
            "person_id": str(b.person_id),
            "channel": "telegram",
            "text": text,
            "update_id": upd.update_id,
        },
    )
    return OK


def _free_text(
    upd: TelegramUpdate, text: str, b: Binding, chat_id: str, now: datetime, d: Deps
) -> dict[str, Any]:
    """Patient free text: store it, route it to the doctor, send ONE template ack (inline, rate limited).

    The system never answers the content. Danger words also raise the Red fast-path draft. Inline
    replies are not outbox rows, so quiet hours and the 3-per-day cap do not apply (same as /start)."""
    assert d.messages is not None and b.patient_id is not None
    if not text:
        return OK  # sticker, photo, voice: nothing to store or answer
    category = tg_text.classify(text)
    m = upd.message or {}
    mid = m.get("message_id")
    inserted, _ = d.messages.save(
        b,
        upd.update_id,
        text,
        category,
        now,
        chat_id=int(chat_id) if chat_id.lstrip("-").isdigit() else None,
        message_id=mid if isinstance(mid, int) else None,
    )
    if not inserted:
        return OK  # repeated update: no second request, no second ack
    d.tasks.enqueue(
        "agent-runs",
        f"tg-{upd.update_id}",
        {"kind": "ingest_event", "person_id": str(b.person_id), "channel": "telegram",
         "update_id": upd.update_id},
    )
    if category == "danger":
        d.fast.red_symptom(b.patient_id, {"recorded_at": now, "update_id": upd.update_id})
    d.audit.audit("tg_free_text", chat=chat_hash(chat_id), category=category)
    urgent = category == "danger"
    if not d.messages.claim_ack(b.person_id, urgent, now, tg_text.ACK_WINDOW_S):
        return OK
    _, reply = tg_text.ack_text(urgent, b.lang, d.messages.first_name(b.person_id))
    return _say(chat_id, reply)


def _active_binding(chat_id: str, d: Deps, now: datetime) -> tuple[Binding | None, str | None]:
    """(binding, refusal_text). Refusal when unbound, inactive or without consent."""
    b = d.bindings.by_chat(chat_id)
    if b is None:
        return None, UNBOUND_TEXT
    if b.status != "active" or not d.consents.has_consent(
        b.person_id, "telegram", "daily_checkin", now
    ):
        return b, STOPPED_TEXT
    return b, None


def _on_callback(upd: TelegramUpdate, d: Deps) -> dict[str, Any]:
    q = upd.callback_query or {}
    tapped_at = d.now()  # callback_query has no date: receipt time is tap time
    msg = q.get("message") or {}
    chat = msg.get("chat") or {}
    if chat.get("type") not in (None, "private"):
        return OK
    chat_id = str((chat.get("id") if chat else None) or (q.get("from") or {}).get("id"))
    qid = q.get("id")

    def answer(text: str) -> dict[str, Any]:
        return {"method": "answerCallbackQuery", "callback_query_id": qid, "text": text}

    b, refusal = _active_binding(chat_id, d, tapped_at)
    if refusal:
        return answer(refusal)
    assert b is not None
    tap = cb.parse(q.get("data"))
    if tap is None or tap.prompt is None:
        return answer("Sorry, that button is not valid.")
    row = d.outbox.get(UUID(tap.prompt))
    if row is None or row.get("recipient_id") != b.person_id:
        d.audit.audit("tg_forged_tap", chat=chat_hash(chat_id))
        return answer("Sorry, that button is not valid.")
    if tap.kind == "c":
        return _dose(upd, q, tap.value or "", row, b, tapped_at, d, answer)
    if tap.kind == "s":
        return _symptom(upd, q, tap, row, b, tapped_at, d, answer, chat_id, msg)
    return answer(NOTED)


def _event(
    upd_id: int, b: Binding, etype: str, at: datetime, payload: dict[str, Any]
) -> dict[str, Any]:
    return {
        "patient_id": b.patient_id,
        "type": etype,
        "occurred_at": at,
        "recorded_at": at,
        "source": "telegram",
        "reporter_id": b.person_id,
        "reporter_mode": "self",
        "channel": "telegram",
        "idempotency_key": f"tg:{upd_id}",
        "payload": payload,
    }


def _save_and_queue(upd_id: int, ev: dict[str, Any], d: Deps) -> bool:
    """Save FIRST, then enqueue. Returns True when the event was newly inserted."""
    _, inserted = d.events.append_event(ev)
    d.tasks.enqueue("agent-runs", f"tg-{upd_id}", {"kind": "tap", "update_id": upd_id})
    return inserted


def _dose(upd, q, code, row, b, at, d, answer):  # noqa: ANN001
    status = cb.DOSE_CODE.get(code)
    if status is None or b.patient_id is None:
        return answer(NOTED)
    sent_at = row.get("sent_at")
    reply_s = max(0, int((at - sent_at).total_seconds())) if sent_at else None
    for_date = row.get("for_date") or clock.ist_date(at)
    payload = {
        "status": status,
        "for_date": str(for_date),
        "prompt_outbox_id": str(row["outbox_id"]),
        "reply_seconds": reply_s,
        "late": bool(reply_s is not None and reply_s > LATE_AFTER_S),
        "proxy": False,
    }
    ev = _event(upd.update_id, b, "DoseCheckin", at, payload)
    inserted = _save_and_queue(upd.update_id, ev, d)
    if inserted and status == "missed":
        d.fast.missed_dose(b.patient_id, ev)
    return answer(NOTED)


def _symptom(upd, q, tap, row, b, at, d, answer, chat_id, msg):  # noqa: ANN001
    mask = tap.mask or 0
    p = tap.prompt
    if tap.value == "t":  # toggle: rewrite keyboard, no event
        mask ^= 1 << (tap.index or 0)
        return {
            "method": "editMessageReplyMarkup",
            "chat_id": chat_id,
            "message_id": msg.get("message_id"),
            "reply_markup": cb.symptom_keyboard(p, mask),
        }
    items = cb.mask_items(0 if tap.value == "n" else mask)
    danger = any(i in cb.DANGER_INDEXES for i in items)
    ev = _event(
        upd.update_id, b, "SymptomReport", at, {"items": items, "codes": [], "danger": danger}
    )
    if b.patient_id is None:
        return answer(NOTED)
    inserted = _save_and_queue(upd.update_id, ev, d)
    if inserted and danger:
        d.fast.red_symptom(b.patient_id, ev)
    return answer(NOTED)
