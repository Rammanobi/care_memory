"""Lane F: outbound Telegram sender. Takes approved outbox rows only.

Checks in order: already sent, approval, channel, binding, consent, banned terms, quiet hours,
3-per-day cap, per-chat rate limit. Then send; honour retry-after; never retry auth errors.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from cm.channels.ports import (
    AuditPort,
    BindingPort,
    ConsentPort,
    EventPort,
    OutboxPort,
    TaskPort,
    TelegramClient,
)
from cm.channels.tg_client import TgAuthError, TgBlocked, TgRetryAfter, TgTransient
from cm.channels.tg_ratelimit import ChatLimiter
from cm.contracts.review import SYSTEM_OUTBOX_KINDS, SendResult
from cm.core import clock
from cm.router.banned import find_banned
from cm.router.quiet_hours import in_quiet_hours, next_open

PROMPT_KINDS = {"checkin", "checkin_nudge", "supporter_proxy"}
QUIET_EXEMPT = {"red_alert", "escalation_notice", "danger_ack"}
DAILY_CAP = 3

# A doctor's reply to a patient question. The outbox column keeps kind 'ai_message' (the DB CHECK and the
# frozen contract list no new kind); a row whose meta carries ``reply_to`` is treated as this logical kind.
NL = chr(10) * 2
QUESTION_REPLY = "question_reply"
CAP_EXEMPT = {QUESTION_REPLY}  # the patient asked: never held back by the 3-per-day cap
_REPLY_LINE = {
    "en": 'Reply to your question: "{q}"',
    "te": 'మీ ప్రశ్నకు సమాధానం: "{q}"',
}
_REPLY_LINE_BARE = {"en": "Reply to your question:", "te": "మీ ప్రశ్నకు సమాధానం:"}


def effective_kind(row: dict[str, Any]) -> str:
    """The sender's view of the kind: 'question_reply' for an approved reply to a patient question."""
    meta = row.get("meta") or {}
    if row.get("kind") == "ai_message" and isinstance(meta.get("reply_to"), dict):
        return QUESTION_REPLY
    return str(row.get("kind"))


def _quiet_exempt(row: dict[str, Any]) -> bool:
    kind = effective_kind(row)
    if kind in QUIET_EXEMPT:
        return True
    # a question reply may skip quiet hours only when the question was urgent
    return kind == QUESTION_REPLY and (row.get("meta") or {}).get("priority") == "urgent"


def reply_text(row: dict[str, Any], lang: str) -> str:
    """First line quotes the patient's question (banned-term clean excerpt), then the doctor's reply."""
    body = row.get("body") or ""
    if effective_kind(row) != QUESTION_REPLY:
        return body
    q = str((row["meta"]["reply_to"]).get("question_excerpt") or "").strip()
    use = lang if lang in _REPLY_LINE else "en"
    head = _REPLY_LINE[use].format(q=q) if q else _REPLY_LINE_BARE[use]
    return head + NL + body


@dataclass
class SenderDeps:
    client: TelegramClient
    outbox: OutboxPort
    bindings: BindingPort
    consents: ConsentPort
    events: EventPort
    tasks: TaskPort
    audit: AuditPort
    limiter: ChatLimiter
    now: Callable[[], datetime]


def has_approval_ref(row: dict[str, Any]) -> bool:
    """Gated kinds need approval_id; system kinds need an approved template_id."""
    if row.get("approval_id"):
        return True
    return bool(row.get("template_id")) and row.get("kind") in SYSTEM_OUTBOX_KINDS


def _purpose(kind: str) -> str:
    return "daily_checkin" if kind in PROMPT_KINDS else "care_coordination"


def _res(row: dict[str, Any], status: str, **kw: Any) -> SendResult:
    return SendResult(outbox_id=row["outbox_id"], status=status, **kw)  # type: ignore[arg-type]


async def send_outbox(row: dict[str, Any], d: SenderDeps) -> SendResult:
    oid, now = row["outbox_id"], d.now()
    if row.get("dedup_key") and d.outbox.already_sent(row["dedup_key"]):
        return _res(row, "skipped", skip_reason="already_sent")
    if not has_approval_ref(row):
        d.outbox.mark(oid, "failed", error="invalid_approval")
        d.audit.audit("tg_send_refused", outbox_id=str(oid), reason="invalid_approval")
        return _res(row, "failed", skip_reason="invalid_approval", error="no approval_ref")
    if row.get("channel") != "telegram":
        return _res(row, "skipped", skip_reason="channel_disabled")
    b = d.bindings.by_person(row["recipient_id"], "telegram")
    if b is None or b.status != "active" or not b.external_id:
        return _res(row, "skipped", skip_reason="no_consent")
    if not d.consents.has_consent(b.person_id, "telegram", _purpose(row["kind"]), now):
        return _res(row, "skipped", skip_reason="no_consent")
    text = reply_text(row, b.lang)
    terms = find_banned(text)
    if terms:
        d.outbox.mark(oid, "failed", error="banned_term")
        d.audit.audit("banned_term_block", outbox_id=str(oid), terms=terms)
        return _res(row, "failed", skip_reason="banned_term", error=",".join(terms))
    if in_quiet_hours(now) and not _quiet_exempt(row):
        wait = (next_open(now) - now).total_seconds()
        return _res(row, "retry", skip_reason="quiet_hours", retry_after_s=wait)
    capped = effective_kind(row) not in CAP_EXEMPT
    if capped and d.outbox.sent_today(row["recipient_id"], clock.ist_date(now)) >= DAILY_CAP:
        return _res(row, "skipped", skip_reason="rate_limit")
    wait = d.limiter.allow(b.external_id)
    if wait > 0:
        return _res(row, "retry", skip_reason="rate_limit", retry_after_s=wait)
    return await _deliver(row, b, text, d)


async def _deliver(row: dict[str, Any], b: Any, text: str, d: SenderDeps) -> SendResult:
    oid, now = row["outbox_id"], d.now()
    meta = row.get("meta") or {}
    markup = meta.get("reply_markup")
    thread = _thread_id(row)
    try:
        if thread is None:
            mid = await d.client.send_message(b.external_id, text, markup)
        else:
            mid = await d.client.send_message(
                b.external_id, text, markup, reply_to_message_id=thread
            )
    except TgRetryAfter as e:
        d.outbox.mark(oid, "pending", next_attempt_at=now + timedelta(seconds=e.seconds))
        return _res(row, "retry", skip_reason="rate_limit", retry_after_s=e.seconds)
    except TgAuthError:
        d.outbox.mark(oid, "failed", error="auth")
        d.audit.audit("tg_auth_error", outbox_id=str(oid))
        return _res(row, "failed", error="auth")  # never retried
    except TgBlocked:
        d.bindings.set_status(b.binding_id, "blocked")
        d.events.append_event(_unreachable(row, b, now))
        d.outbox.mark(oid, "failed", error="blocked")
        return _res(row, "failed", error="blocked")
    except TgTransient as e:
        d.outbox.mark(oid, "pending", next_attempt_at=now + timedelta(seconds=30))
        return _res(row, "retry", error=str(e), retry_after_s=30)
    d.outbox.mark(oid, "sent", provider_message_id=mid, sent_at=now)
    if row["kind"] in PROMPT_KINDS:
        _record_prompt(row, b, mid, now, d)
    return _res(row, "sent", provider_message_id=mid)


def _thread_id(row: dict[str, Any]) -> int | None:
    """Telegram message id of the patient's question, so the reply is threaded under it."""
    if effective_kind(row) != QUESTION_REPLY:
        return None
    mid = row["meta"]["reply_to"].get("telegram_message_id")
    return mid if isinstance(mid, int) and not isinstance(mid, bool) else None


def _unreachable(row: dict[str, Any], b: Any, now: datetime) -> dict[str, Any]:
    return {
        "patient_id": b.patient_id,
        "type": "ChannelUnreachable",
        "occurred_at": now,
        "recorded_at": now,
        "source": "system",
        "reporter_mode": "record",
        "channel": "telegram",
        "idempotency_key": f"unreach:{row['outbox_id'].hex}",
        "payload": {"reason": "blocked", "detail": None},
    }


def _record_prompt(row: dict[str, Any], b: Any, mid: str, now: datetime, d: SenderDeps) -> None:
    if b.patient_id is None:
        return
    channel = "supporter_proxy" if row["kind"] == "supporter_proxy" else "telegram"
    d.events.append_event(
        {
            "patient_id": b.patient_id,
            "type": "CheckinPrompt",
            "occurred_at": now,
            "recorded_at": now,
            "source": "system",
            "reporter_mode": "record",
            "channel": channel,
            "idempotency_key": f"prompt:{row['outbox_id']}",
            "payload": {
                "outbox_id": str(row["outbox_id"]),
                "for_date": str(row.get("for_date") or clock.ist_date(now)),
                "sent_at": now.isoformat(),
                "provider_message_id": mid,
            },
        }
    )
    if row["kind"] == "checkin":
        d.tasks.enqueue(
            "outbound", f"nudge-{row['outbox_id'].hex}", {"outbox_id": str(row["outbox_id"])}
        )
