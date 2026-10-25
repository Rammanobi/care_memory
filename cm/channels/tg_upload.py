"""Lane F: Telegram photo and document intake. Plain Python, no LLM.

A bound, consented patient chat can send a photo (largest size) or a document. The bytes are fetched through
the injected ``files`` callable (``HttpTelegramClient.fetch_file``: getFile, then the file URL, with retry),
handed to ``cm.uploads.intake.accept_upload`` and answered with ONE approved template. This module never
decides anything about the content, never logs the file name, and never sees the bot token: the file URL
contains the token, so only the client builds it and every client error is rewrapped without it.
"""

from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from cm.channels import tg_text
from cm.channels.binding import STOPPED_TEXT, chat_hash
from cm.channels.ports import Binding
from cm.channels.tg_client import TgError

MAX_BYTES = 10 * 1024 * 1024  # fallback only: the live limit is cm.uploads.validate.max_bytes() (UPLOAD_MAX_MB)
RATE_LIMIT_FALLBACK = 5
TGFILE_KIND = "tgfile"
MAX_NAME = 120
ACK_TEMPLATE = "upload_ack_v1"
REJECTED_TEMPLATE = "upload_rejected_v1"
REJECT_REASONS = {"too_large", "bad_type", "storage_error", "unknown_patient"}
SILENT_REASONS = {"rate_limited", "duplicate"}
EXTRACT_KIND = "document_extract"
_SAFE = re.compile(r"[^\w.\- ()]+", re.UNICODE)


@dataclass(frozen=True)
class FileRef:
    file_id: str
    unique_id: str
    name: str
    mime: str
    size: int | None


@dataclass
class Outcome:
    reply: dict[str, Any] | None = None
    rejected: bool = False


def _accept_upload(**kw: Any) -> Any:
    """Late import: the intake lives in cm.uploads (another lane). Tests monkeypatch this function."""
    from cm.uploads.intake import accept_upload

    return accept_upload(**kw)


def max_bytes() -> int:
    try:
        from cm.uploads.validate import max_bytes as live

        return int(live())
    except Exception:  # noqa: BLE001 - validate missing or broken: the documented default
        return MAX_BYTES


def _find_by_origin(token: str, key: str) -> Any:
    from cm.store import uploads_repo

    return uploads_repo.find_by_origin(token, key)


def _count_recent(token: str) -> int:
    from cm.store import uploads_repo

    return int(uploads_repo.count_recent(token, 3600))


def _consent_ok(token: str) -> bool:
    """Telegram upload consent right now (same rule as the intake). A lookup error defers to the intake."""
    try:
        from cm.uploads.intake import has_upload_consent

        return has_upload_consent(token, "telegram")
    except Exception:  # noqa: BLE001
        return True


def _rate_limit() -> int:
    try:
        from cm.uploads.intake import RATE_LIMIT

        return int(RATE_LIMIT)
    except Exception:  # noqa: BLE001
        return RATE_LIMIT_FALLBACK


def _clean_name(name: str, fallback: str) -> str:
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = _SAFE.sub("_", base).strip(" .")[:MAX_NAME]
    return base or fallback


def _largest_photo(sizes: list[Any]) -> dict[str, Any] | None:
    photos = [p for p in sizes if isinstance(p, dict) and p.get("file_id")]
    if not photos:
        return None
    return max(
        photos,
        key=lambda p: (int(p.get("file_size") or 0), int(p.get("width") or 0) * int(p.get("height") or 0)),
    )


def _size(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def extract(m: dict[str, Any]) -> FileRef | None:
    """The file in a Telegram message: a document, else the largest photo size. None for anything else."""
    doc = m.get("document")
    if isinstance(doc, dict) and doc.get("file_id"):
        uid = str(doc.get("file_unique_id") or doc["file_id"])
        name = _clean_name(str(doc.get("file_name") or ""), f"telegram_{uid}")
        mime = str(doc.get("mime_type") or mimetypes.guess_type(name)[0] or "application/octet-stream")
        return FileRef(str(doc["file_id"]), uid, name, mime.lower(), _size(doc.get("file_size")))
    photo = _largest_photo(m["photo"]) if isinstance(m.get("photo"), list) else None
    if photo:
        uid = str(photo.get("file_unique_id") or photo["file_id"])
        return FileRef(str(photo["file_id"]), uid, f"photo_{uid}.jpg", "image/jpeg", _size(photo.get("file_size")))
    return None


def _say(chat_id: str, text: str) -> dict[str, Any]:
    return {"method": "sendMessage", "chat_id": chat_id, "text": text}


def _template(tid: str, b: Binding, chat_id: str, d: Any) -> dict[str, Any] | None:
    try:
        name = d.messages.first_name(b.person_id) if d.messages else None
        text = tg_text.template_text(tid, b.lang, name)
    except (KeyError, ValueError):
        d.audit.audit("tg_upload_template_missing", template=tid)
        return None  # never invent patient text: no approved template, no reply
    return _say(chat_id, text)


def _reject(b: Binding, chat_id: str, d: Any, reason: str) -> Outcome:
    d.audit.audit("tg_upload_rejected", chat=chat_hash(chat_id), reason=reason)
    return Outcome(_template(REJECTED_TEMPLATE, b, chat_id, d), rejected=True)


def _ack(b: Binding, chat_id: str, now: datetime, d: Any) -> Outcome:
    if d.messages is None or not d.messages.claim_ack(b.person_id, False, now, tg_text.ACK_WINDOW_S):
        return Outcome()
    return Outcome(_template(ACK_TEMPLATE, b, chat_id, d))


def _download(ref: FileRef, d: Any) -> bytes | str:
    """The bytes, or a rejection reason. Only ever records the error class, never its text."""
    from cm.channels.tg_http import TgFileTooLarge

    try:
        return d.files(ref.file_id, max_bytes())
    except TgFileTooLarge:
        return "too_large"
    except TgError as exc:
        d.audit.audit("tg_upload_fetch_failed", error=type(exc).__name__)
        return "storage_error"
    except Exception as exc:  # noqa: BLE001 - one bad file must not break the update loop
        d.audit.audit("tg_upload_fetch_failed", error=type(exc).__name__)
        return "storage_error"


def _skip_reason(token: str, ref: FileRef, d: Any) -> str | None:
    """Cheap checks BEFORE any download: replay of the same Telegram file, or the hourly rate limit.
    A database hiccup here never blocks the upload: the intake re-checks everything."""
    try:
        if _find_by_origin(token, f"telegram:{ref.unique_id}"):
            return "duplicate"
        if _count_recent(token) >= _rate_limit():
            return "rate_limited"
    except Exception as exc:  # noqa: BLE001
        d.audit.audit("tg_upload_precheck_failed", error=type(exc).__name__)
    return None


def handle(m: dict[str, Any], ref: FileRef, b: Binding, chat_id: str, now: datetime, d: Any) -> Outcome:
    """Intake one file from a bound, consented patient chat. Returns the (single) inline reply, if any.

    Consent is checked by the caller (active binding + telegram consent) before this runs. Order here:
    declared size, patient token, origin dedupe, rate limit, then the download. On the webhook path the
    download is NOT done here (it can take seconds): a ``tgfile`` task does it after the 200 is sent."""
    if d.files is None or d.patient_token is None:
        d.audit.audit("tg_upload_unavailable", chat=chat_hash(chat_id))
        return Outcome()
    if ref.size is not None and ref.size > max_bytes():
        return _reject(b, chat_id, d, "too_large")  # refused on the declared size, nothing downloaded
    token = d.patient_token(b.person_id)
    if not token:
        return _reject(b, chat_id, d, "unknown_patient")
    skip = _skip_reason(token, ref, d)
    if skip == "duplicate":
        d.audit.audit("tg_upload_duplicate", chat=chat_hash(chat_id))
        return Outcome()
    if skip:
        d.audit.audit("tg_upload_rejected", chat=chat_hash(chat_id), reason=skip)
        return Outcome()
    mid = m.get("message_id")
    if not getattr(d, "inline_files", False):
        task_id = "tgfile-" + re.sub(r"[^A-Za-z0-9_-]", "_", ref.unique_id)[:200]
        d.tasks.enqueue("agent-runs", task_id, {
            "kind": TGFILE_KIND, "person_id": str(b.person_id), "chat_id": chat_id,
            "message_id": mid if isinstance(mid, int) else None, "file_id": ref.file_id,
            "unique_id": ref.unique_id, "name": ref.name, "mime": ref.mime, "size": ref.size,
        })
        d.audit.audit("tg_upload_queued", chat=chat_hash(chat_id))
        return _ack(b, chat_id, now, d)
    got = _download(ref, d)
    if isinstance(got, str):
        return _reject(b, chat_id, d, got)
    try:
        res = _accept_upload(**_intake_kwargs(token, ref, got, b.person_id, chat_id, mid))
    except Exception as exc:  # noqa: BLE001 - intake bugs must not loop the poller on one update
        d.audit.audit("tg_upload_error", chat=chat_hash(chat_id), error=type(exc).__name__)
        return _reject(b, chat_id, d, "storage_error")
    return _result(res, b, chat_id, now, d)


def _intake_kwargs(token: str, ref: FileRef, data: bytes, person_id: Any, chat_id: str, mid: Any) -> dict[str, Any]:
    cid: int | str = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
    return {
        "patient_token": token, "source": "telegram", "filename": ref.name, "mime": ref.mime, "data": data,
        "uploader_person_id": person_id,
        "origin": {
            "telegram_file_unique_id": ref.unique_id,
            "telegram_chat_id": cid,
            "telegram_message_id": mid if isinstance(mid, int) else None,
        },
    }


def run_tgfile_task(payload: dict[str, Any], *, fetch: Any = None, audit: Any = None, enqueue: Any = None) -> str:
    """Worker side of the ``tgfile`` task: fetch the file, hand it to the intake, enqueue extraction.

    Returns a short outcome word. Retryable download errors are re-raised (token-free TgFileError) so the
    queue retries; permanent ones are audited and acked. The payload never carries the bot token."""
    from uuid import UUID

    from cm.channels.tg_http import TgFileTooLarge
    from cm.store import upload_channels_repo

    def note(event: str, **kw: Any) -> None:
        if audit is not None:
            audit.audit(event, **kw)
        else:
            from cm.core.logging import get_logger

            get_logger(__name__).info(event, **kw)

    if fetch is None:
        from cm.channels.tg_http import HttpTelegramClient

        fetch = HttpTelegramClient().fetch_file
    if enqueue is None:
        from cm.core import tasks

        enqueue = tasks.enqueue
    pid = UUID(str(payload["person_id"]))
    token = upload_channels_repo.person_token(pid)
    ref = FileRef(str(payload["file_id"]), str(payload["unique_id"]), str(payload.get("name") or "file"),
                  str(payload.get("mime") or "application/octet-stream"), _size(payload.get("size")))
    if not token:
        note("tg_upload_rejected", reason="unknown_patient")
        return "unknown_patient"
    if _find_by_origin(token, f"telegram:{ref.unique_id}"):
        note("tg_upload_duplicate")
        return "duplicate"
    if not _consent_ok(token):  # /stop (consent withdrawn) after the file was queued: never download it
        note("tg_upload_no_consent")
        return "no_consent"
    try:
        data = fetch(ref.file_id, max_bytes())
    except TgFileTooLarge:
        note("tg_upload_rejected", reason="too_large")
        return "too_large"
    except TgError as exc:
        note("tg_upload_fetch_failed", error=type(exc).__name__)
        if getattr(exc, "error_class", None) == "retryable":
            raise
        return "storage_error"
    res = _accept_upload(**_intake_kwargs(token, ref, data, pid, str(payload.get("chat_id") or ""),
                                          payload.get("message_id")))
    reason, doc_id = getattr(res, "reason", None), getattr(res, "document_id", None)
    if getattr(res, "duplicate", False) or reason == "duplicate":
        note("tg_upload_duplicate")
        return "duplicate"
    if reason or doc_id is None:
        note("tg_upload_rejected", reason=reason or "storage_error")
        return reason or "storage_error"
    enqueue("agent-runs", f"docx-{doc_id}", {"kind": EXTRACT_KIND, "document_id": str(doc_id)})
    note("tg_upload_accepted")
    return "accepted"


def _result(res: Any, b: Binding, chat_id: str, now: datetime, d: Any) -> Outcome:
    reason = getattr(res, "reason", None)
    doc_id = getattr(res, "document_id", None)
    if getattr(res, "duplicate", False) or reason == "duplicate":
        d.audit.audit("tg_upload_duplicate", chat=chat_hash(chat_id))
        return Outcome()
    if reason == "no_consent":
        d.audit.audit("tg_upload_no_consent", chat=chat_hash(chat_id))
        return Outcome(_say(chat_id, STOPPED_TEXT))
    if reason in SILENT_REASONS:
        d.audit.audit("tg_upload_rejected", chat=chat_hash(chat_id), reason=reason)
        return Outcome()
    if reason or doc_id is None:
        return _reject(b, chat_id, d, reason if reason in REJECT_REASONS else "storage_error")
    # Same task id as the intake uses, so a second enqueue is a no-op (cm.core.tasks drops a repeated name).
    d.tasks.enqueue("agent-runs", f"docx-{doc_id}", {"kind": EXTRACT_KIND, "document_id": str(doc_id)})
    d.audit.audit("tg_upload_accepted", chat=chat_hash(chat_id))
    return _ack(b, chat_id, now, d)


def pick_reply(cap: dict[str, Any] | None, up: Outcome, urgent: bool) -> dict[str, Any] | None:
    """ONE inline reply per update: urgent caption ack, a rejection, the caption ack, then the upload ack."""
    cap_say = cap if cap and cap.get("method") else None
    if urgent and cap_say:
        return cap_say
    if up.rejected and up.reply:
        return up.reply
    return cap_say or up.reply
