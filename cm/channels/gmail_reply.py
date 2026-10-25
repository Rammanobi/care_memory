"""Lane M: verify a doctor's reply and apply it through decide() (F5 steps 6-9)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parseaddr
from typing import Any
from uuid import UUID

from cm.channels.gmail import token_hash
from cm.channels.gmail_parse import MAX_ITEMS, parse_reply
from cm.channels.ports_gmail import AuditLog, DecideFn, OutboxWriter, TokenStore
from cm.contracts.review import ReviewDecisionIn

_PLUS_TAG = re.compile(r"\+r_([A-Za-z0-9_\-]{8,64})@")
DEFAULT_REJECT_REASON = "Rejected by email reply (no reason given)"


@dataclass
class ReplyOutcome:
    refused: str | None = None            # reason when nothing was applied at all
    applied: list[int] = field(default_factory=list)
    edited: list[int] = field(default_factory=list)
    skipped: dict[int, str] = field(default_factory=dict)
    clarification: bool = False
    echo_text: str = ""


_ADDR = re.compile(r"[^\s<>\"',;:()]+@[^\s<>\"',;:()]+")


def _one_address(value: str) -> bool:
    """Exactly one distinct address in the header. parseaddr reads 'doc@clinic <evil@x>' as doc@clinic, while
    DMARC aligns on evil@x: a header carrying two addresses is never trusted."""
    return len({a.lower().rstrip(".") for a in _ADDR.findall(value or "")}) == 1


def sender_ok(headers: dict[str, str], doctor_email: str) -> bool:
    """From must equal the registered doctor AND authentication must pass (dmarc, or dkim+spf)."""
    if not _one_address(headers.get("from", "")):
        return False
    if parseaddr(headers.get("from", ""))[1].lower() != doctor_email.lower():
        return False
    sender_hdr = parseaddr(headers.get("sender", ""))[1].lower()
    if sender_hdr and sender_hdr != doctor_email.lower():
        return False
    auth = headers.get("authentication-results", "").lower()
    return "dmarc=pass" in auth or ("dkim=pass" in auth and "spf=pass" in auth)


def extract_token(headers: dict[str, str]) -> str | None:
    for key in ("delivered-to", "to"):
        if m := _PLUS_TAG.search(headers.get(key, "")):
            return m.group(1)
    return None


def is_forwarded(headers: dict[str, str]) -> bool:
    return bool(re.match(r"\s*(fwd?|fw):", headers.get("subject", ""), re.I))


def thread_ok(headers: dict[str, str], doctor_id: str) -> bool:
    refs = headers.get("in-reply-to", "") + " " + headers.get("references", "")
    return f"<digest-{doctor_id}-" in refs


def _refuse(reason: str, msg: dict[str, Any], audit: AuditLog | None) -> ReplyOutcome:
    if audit:
        audit.record("gmail_reply_refused", reason=reason, message_id=msg["id"])
    return ReplyOutcome(refused=reason,
                        echo_text="We could not apply your reply, and nothing was changed. Please use the console.")


def handle_reply(msg: dict[str, Any], *, doctor_id: str, doctor_email: str, tokens: TokenStore,
                 decide: DecideFn, now: datetime, outbox: OutboxWriter | None = None,
                 audit: AuditLog | None = None, console_url: str = "") -> ReplyOutcome:
    """Run every check, then decide() per item. Any failed check applies nothing and is audited."""
    h = msg["headers"]
    if not sender_ok(h, doctor_email):
        return _refuse("sender_not_verified", msg, audit)      # no echo to a spoofer
    if is_forwarded(h):
        return _refuse("forwarded", msg, audit)
    if not thread_ok(h, doctor_id):
        return _refuse("wrong_thread", msg, audit)
    t = extract_token(h)
    if t is None:
        return _refuse("no_token", msg, audit)

    parsed = parse_reply(msg.get("text", ""))
    if parsed.needs_clarification:
        out = ReplyOutcome(clarification=True, echo_text=clarification_text(parsed.unknown_lines))
        _echo(out, msg, doctor_email, outbox)
        return out

    out = ReplyOutcome()
    done: set[int] = set()
    for cmd in parsed.parse.commands:
        for n in cmd.items or range(1, MAX_ITEMS + 1):
            if n in done:
                continue
            status, approval_id = tokens.consume(token_hash(t, n), doctor_id, now)
            if status != "ok":
                if cmd.items:   # ALL stops silently at the first miss
                    out.skipped[n] = {"used": "already applied", "expired": "link expired"}.get(status, "not recognised")
                    done.add(n)
                    continue
                break
            done.add(n)
            _apply(out, n, cmd.verb, cmd.text, approval_id, token_hash(t, n), tokens, decide, doctor_id)
    out.echo_text = echo_text(out, console_url)
    if audit:
        audit.record("gmail_reply_applied", message_id=msg["id"], applied=out.applied, skipped=list(out.skipped))
    _echo(out, msg, doctor_email, outbox)
    return out


def _apply(out: ReplyOutcome, n: int, verb: str, text: str | None, approval_id: UUID | None, th: str,
           tokens: TokenStore, decide: DecideFn, doctor_id: str) -> None:
    action = {"approve": "approve", "reject": "reject", "edit": "edit"}[verb]
    body = ReviewDecisionIn(
        action=action,  # type: ignore[arg-type]
        edited={"body": text} if verb == "edit" else None,
        reason=(text or DEFAULT_REJECT_REASON) if verb == "reject" else None,
    )
    try:
        res = decide(approval_id, body, via="gmail", actor=doctor_id)  # type: ignore[arg-type]
    except Exception:
        tokens.release(th)
        out.skipped[n] = "could not be applied, please use the console"
        return
    if res.error_code == "already_decided":
        out.skipped[n] = "already decided in console"
    elif res.error_code:
        tokens.release(th)   # nothing was decided: keep the link usable (e.g. retry with corrected text)
        out.skipped[n] = res.error_code.replace("_", " ")
    else:
        (out.edited if verb == "edit" else out.applied).append(n)


def echo_text(out: ReplyOutcome, console_url: str = "") -> str:
    parts = []
    if out.applied:
        parts.append("done: " + ", ".join(map(str, sorted(out.applied))))
    if out.edited:
        parts.append("edited: " + ", ".join(map(str, sorted(out.edited))))
    for n, why in sorted(out.skipped.items()):
        parts.append(f"skipped {n} ({why})")
    parts.append("Red items need the console.")
    return "Applied. " + " | ".join(parts)


def clarification_text(unknown: list[str]) -> str:
    return ("We did not understand your reply, so nothing was changed. Please reply with lines such as:\n"
            "APPROVE 1-5\nAPPROVE ALL\nREJECT 3: reason\nEDIT 3: new text\n"
            + ("\nNot understood: " + "; ".join(unknown[:3]) if unknown else ""))


def _echo(out: ReplyOutcome, msg: dict[str, Any], doctor_email: str, outbox: OutboxWriter | None) -> None:
    if outbox is None:
        return
    outbox.enqueue_echo(dedup_key=f"echo:{msg['id']}", to=doctor_email, subject="Re: " + msg["headers"].get("subject", "CareMemory review"),
                        body_text=out.echo_text, thread_id=msg.get("thread_id"),
                        in_reply_to=msg["headers"].get("message-id"))
