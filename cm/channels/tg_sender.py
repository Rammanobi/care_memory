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
    text = row.get("body") or ""
    terms = find_banned(text)
    if terms:
        d.outbox.mark(oid, "failed", error="banned_term")
        d.audit.audit("banned_term_block", outbox_id=str(oid), terms=terms)
        return _res(row, "failed", skip_reason="banned_term", error=",".join(terms))
    if in_quiet_hours(now) and row["kind"] not in QUIET_EXEMPT:
        wait = (next_open(now) - now).total_seconds()
        return _res(row, "retry", skip_reason="quiet_hours", retry_after_s=wait)
    if d.outbox.sent_today(row["recipient_id"], clock.ist_date(now)) >= DAILY_CAP:
        return _res(row, "skipped", skip_reason="rate_limit")
    wait = d.limiter.allow(b.external_id)
    if wait > 0:
        return _res(row, "retry", skip_reason="rate_limit", retry_after_s=wait)
    return await _deliver(row, b, text, d)


async def _deliver(row: dict[str, Any], b: Any, text: str, d: SenderDeps) -> SendResult:
    oid, now = row["outbox_id"], d.now()
    markup = (row.get("meta") or {}).get("reply_markup")
    try:
        mid = await d.client.send_message(b.external_id, text, markup)
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
