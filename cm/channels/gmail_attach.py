"""Lane M: attachments on an inbound doctor email become patient document uploads.

Rules (all enforced here, none by trust):
* Only a sender on ``DOCTOR_EMAIL_ALLOWLIST`` whose From passes the same authentication check as
  approve-by-reply (``gmail_reply.sender_ok``). Anyone else is ignored and audited.
* The message must carry exactly one patient code (``PT-0906``) in the subject or body, else nothing is stored.
* Every attachment goes through ``cm.uploads.intake.accept_upload`` (source ``gmail``), which owns the size,
  type, consent, duplicate and rate rules. Nothing is approved here and nothing is sent to anyone: this path
  never writes to the outbox, never calls ``decide`` and never replies by email.
* The audit log records message and attachment ids and reasons, never file names or file content.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from email.utils import parseaddr
from typing import Any
from uuid import UUID

from cm.channels.gmail import call_with_retry
from cm.channels.gmail_reply import extract_token, sender_ok
from cm.channels.ports_gmail import AuditLog, GmailApi

MAX_BYTES = 10 * 1024 * 1024  # fallback only: the live limit is cm.uploads.validate.max_bytes()
EXTRACT_KIND = "document_extract"
CODE_RE = re.compile(r"\bPT-(\d{4})\b", re.IGNORECASE)  # exactly 4 digits: persons.token is ^P-[0-9]{4}$
_SILENT = {"duplicate"}


@dataclass
class AttachResult:
    handled: bool = False                 # the message carried attachments and reached the upload lane
    refused: str | None = None            # reason nothing was stored at all
    patient_token: str | None = None
    accepted: list[str] = field(default_factory=list)       # attachment ids stored
    duplicates: list[str] = field(default_factory=list)
    rejected: dict[str, str] = field(default_factory=dict)  # attachment id -> reason


def _accept_upload(**kw: Any) -> Any:
    """Late import: the intake lives in cm.uploads (another lane). Tests monkeypatch this function."""
    from cm.uploads.intake import accept_upload

    return accept_upload(**kw)


def _max_bytes() -> int:
    try:
        from cm.uploads.validate import max_bytes

        return int(max_bytes())
    except Exception:  # noqa: BLE001 - validate missing: documented default
        return MAX_BYTES


def allowlist_from_env(env: dict[str, str] | None = None) -> tuple[str, ...]:
    e = os.environ if env is None else env
    return tuple(a.strip().lower() for a in e.get("DOCTOR_EMAIL_ALLOWLIST", "").split(",") if a.strip())


def find_patient_code(msg: dict[str, Any]) -> str | None:
    """The one patient code in the subject (preferred) or body, as a person token ('P-0906').

    Two different codes in the same place are ambiguous: None, so a file is never filed to a guess."""
    for text in (msg.get("headers", {}).get("subject", ""), msg.get("text", "")):
        codes = {m.group(1) for m in CODE_RE.finditer(text or "")}
        if len(codes) == 1:
            return "P-" + codes.pop()
        if len(codes) > 1:
            return None
    return None


def _audit(audit: AuditLog | None, event: str, **fields: Any) -> None:
    if audit is not None:
        audit.record(event, **fields)


def _default_enqueue(queue: str, name: str, payload: dict[str, Any]) -> None:
    from cm.core import tasks

    tasks.enqueue(queue, name, payload)


def handle_attachments(
    msg: dict[str, Any],
    *,
    api: GmailApi,
    allowlist: Iterable[str],
    resolve_doctor: Callable[[str], UUID | None],
    audit: AuditLog | None = None,
    enqueue: Callable[[str, str, dict[str, Any]], None] = _default_enqueue,
    sleep: Callable[[float], None] = time.sleep,
    max_bytes: int | None = None,
) -> AttachResult:
    """Upload the attachments of one normalised inbound message. Quota and transient Gmail errors propagate
    so the fetch task retries (the message is only marked processed after this returns)."""
    atts = [a for a in (msg.get("attachments") or []) if a.get("attachment_id")]
    res = AttachResult()
    max_bytes = _max_bytes() if max_bytes is None else max_bytes
    if not atts:
        return res
    res.handled = True
    mid = msg["id"]
    email = parseaddr(msg.get("headers", {}).get("from", ""))[1].lower()
    if email not in {a.lower() for a in allowlist} or not sender_ok(msg.get("headers", {}), email):
        res.refused = "sender_not_allowlisted"
        _audit(audit, "gmail_upload_refused", reason=res.refused, message_id=mid)
        return res
    token = find_patient_code(msg)
    if token is None:
        res.refused = "no_patient_code"
        _audit(audit, "gmail_upload_refused", reason=res.refused, message_id=mid)
        return res
    res.patient_token = token
    doctor = resolve_doctor(email)
    for att in atts:
        _one(att, msg, token, doctor, res, api=api, audit=audit, enqueue=enqueue, sleep=sleep, max_bytes=max_bytes)
    return res


def _one(att: dict[str, Any], msg: dict[str, Any], token: str, doctor: UUID | None, res: AttachResult, *,
         api: GmailApi, audit: AuditLog | None, enqueue: Callable[[str, str, dict[str, Any]], None],
         sleep: Callable[[float], None], max_bytes: int) -> None:
    mid, aid = msg["id"], att["attachment_id"]

    def reject(reason: str) -> None:
        res.rejected[aid] = reason
        _audit(audit, "gmail_upload_rejected", reason=reason, message_id=mid, attachment_id=aid)

    size = att.get("size")
    if isinstance(size, int) and size > max_bytes:
        return reject("too_large")  # declared size: nothing fetched
    data = call_with_retry(lambda: api.fetch_attachment(mid, aid), sleep=sleep)
    if len(data) > max_bytes:
        return reject("too_large")
    try:
        out = _accept_upload(
            patient_token=token, source="gmail", filename=att.get("filename") or f"attachment_{aid[:8]}",
            mime=(att.get("mime") or "application/octet-stream").lower(), data=data, uploader_person_id=doctor,
            origin={"gmail_message_id": mid, "gmail_attachment_id": aid},
        )
    except Exception as exc:  # noqa: BLE001 - one bad attachment must not stop the others or loop the task
        _audit(audit, "gmail_upload_error", message_id=mid, attachment_id=aid, error=type(exc).__name__)
        return reject("storage_error")
    reason, doc_id = getattr(out, "reason", None), getattr(out, "document_id", None)
    if getattr(out, "duplicate", False) or reason in _SILENT:
        res.duplicates.append(aid)
        _audit(audit, "gmail_upload_duplicate", message_id=mid, attachment_id=aid)
    elif reason or doc_id is None:
        reject(reason or "storage_error")
    else:
        res.accepted.append(aid)
        enqueue("agent-runs", f"docx-{doc_id}", {"kind": EXTRACT_KIND, "document_id": str(doc_id)})
        _audit(audit, "gmail_upload_accepted", message_id=mid, attachment_id=aid)


def dispatch(msg: dict[str, Any], *, on_reply: Callable[[dict[str, Any]], None] | None = None,
             **attach: Any) -> AttachResult:
    """``on_message`` for ``fetch_worker``. A message that looks like a doctor reply (plus-tag token in
    To/Delivered-To, or In-Reply-To/References a digest) ALWAYS goes to ``on_reply`` first; attachments are
    handled in addition, never instead (so a reply with a signature logo still applies the approval).
    ``attach`` are the ``handle_attachments`` keywords. Library path: no runtime caller wires this yet."""
    if on_reply is not None and (not msg.get("attachments") or is_reply_like(msg)):
        on_reply(msg)
    if msg.get("attachments"):
        return handle_attachments(msg, **attach)
    return AttachResult()


def is_reply_like(msg: dict[str, Any]) -> bool:
    h = msg.get("headers", {})
    refs = h.get("in-reply-to", "") + " " + h.get("references", "")
    return extract_token(h) is not None or "<digest-" in refs
