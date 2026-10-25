"""accept_upload: the single entry point every channel (portal, Telegram, Gmail) uses to take in a document.

Never raises. Order: patient, consent, origin idempotency, validation, content dedupe, rate limit, store, insert.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from cm.core import clock
from cm.core.db import transaction
from cm.core.logging import get_logger
from cm.store import consent as consent_repo
from cm.store import uploads_repo
from cm.uploads.storage import StoragePort, get_storage
from cm.uploads.validate import UploadRejected, validate_upload

log = get_logger(__name__)
RATE_LIMIT = 5  # uploads per patient per hour; WALL time on purpose (abuse guard, not a record read: no as_of)
RATE_WINDOW_S = 3600
# Consent ledger sources that let a patient store documents sent through each channel (any granted purpose).
_CONSENT_SOURCES = {
    "portal": ("portal", "web", "telegram", "gmail"),
    "telegram": ("telegram", "web"),
    "gmail": ("gmail", "web"),
}


@dataclass
class UploadResult:
    document_id: str | None
    status: str  # internal upload_state, or "rejected"
    duplicate: bool = False
    # no_consent|too_large|bad_type|rate_limited|unknown_patient|storage_error|duplicate|internal_error
    reason: str | None = None


def _fail(reason: str) -> UploadResult:
    return UploadResult(None, "rejected", False, reason)


def origin_key(origin: dict[str, Any] | None) -> str | None:
    """Stable idempotency key from the channel's own ids (Telegram file_unique_id, Gmail message+attachment)."""
    o = origin or {}
    if o.get("telegram_file_unique_id"):
        return f"telegram:{o['telegram_file_unique_id']}"
    if o.get("gmail_message_id") and o.get("gmail_attachment_id"):
        return f"gmail:{o['gmail_message_id']}:{o['gmail_attachment_id']}"
    return None


def _dup(row: dict[str, Any]) -> UploadResult:
    return UploadResult(
        str(row["document_id"]), row["extra"].get("upload_state", "received"), True, "duplicate"
    )


def _consent(conn: Any, person_id: UUID, source: str, at: Any) -> UUID | None:
    state = consent_repo.consent_state(person_id, at, conn=conn)
    for src in _CONSENT_SOURCES.get(source, (source,)):
        if any(v == "granted" for v in state.get(src, {}).values()):
            return consent_repo.latest_consent_id(person_id, src, at, conn=conn)
    return None


def has_upload_consent(patient_token: str, channel: str, at: Any = None) -> bool:
    """Does the patient still allow documents from ``channel`` (same rule as intake)? Used again at approval."""
    with transaction() as conn:
        pat = conn.execute(
            "SELECT p.person_id FROM cm.persons p JOIN cm.patients pt USING (person_id) "
            "WHERE p.token=%s AND p.role='patient'",
            (patient_token,),
        ).fetchone()
        return bool(pat) and _consent(conn, pat["person_id"], channel, at or clock.now()) is not None


def content_hash(patient_token: str, data: bytes) -> bytes:
    """Per patient: cm.documents.content_hash is globally unique, so two patients never collide."""
    return hashlib.sha256(b"upload:" + patient_token.encode() + b":" + data).digest()


def accept_upload(
    *,
    patient_token: str,
    source: str,
    filename: str,
    mime: str,
    data: bytes,
    uploader_person_id: UUID | None = None,
    origin: dict[str, Any] | None = None,
    storage: StoragePort | None = None,
) -> UploadResult:
    try:
        return _accept(
            patient_token, source, filename, mime, data, uploader_person_id, origin, storage
        )
    except Exception as exc:  # noqa: BLE001  (contract: never raises)
        log.error("upload_intake_failed", error=type(exc).__name__)
        return _fail("internal_error")


def _accept(
    token: str,
    source: str,
    filename: str,
    mime: str,
    data: bytes,
    uploader: UUID | None,
    origin: dict[str, Any] | None,
    storage: StoragePort | None,
) -> UploadResult:
    at = clock.now()
    okey = origin_key(origin)
    chash = content_hash(token, data)
    with transaction() as conn:
        pat = conn.execute(
            "SELECT p.person_id FROM cm.persons p JOIN cm.patients pt USING (person_id) "
            "WHERE p.token=%s AND p.role='patient'",
            (token,),
        ).fetchone()
        if not pat:
            return _fail("unknown_patient")
        consent_id = _consent(conn, pat["person_id"], source, at)
        if consent_id is None:
            return _fail("no_consent")
        uploads_repo.lock_patient(token, conn=conn)  # concurrent uploads: count and dedupe see each other
        if okey and (row := uploads_repo.find_by_origin(token, okey, conn=conn)):
            return _dup(row)
        try:
            v = validate_upload(filename, data, mime)
        except UploadRejected as exc:
            return _fail(exc.code)
        if (row := uploads_repo.find_by_hash(chash, conn=conn)) and row["patient_token"] == token:
            return _dup(row)
        # Serialise the read-then-insert per patient: the lock lasts until this transaction commits.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"upload_rate:{token}",))
        if uploads_repo.count_recent(token, RATE_WINDOW_S, conn=conn) >= RATE_LIMIT:
            return _fail("rate_limited")
        sha = hashlib.sha256(data).hexdigest()
        try:
            uri = (storage or get_storage()).put(f"{token}/{sha}", data)
        except Exception:  # noqa: BLE001
            return _fail("storage_error")
        extra = {
            "filename": v.filename,
            "mime": v.mime,
            "size": v.size,
            "pages": v.pages,
            "sha256": sha,
            "storage_uri": uri,
            "channel": source,
            "origin_key": okey,
            "uploader_person_id": str(uploader) if uploader else None,
            "origin": {k: str(x) for k, x in (origin or {}).items()},
        }
        doc_id = uploads_repo.insert(
            patient_token=token,
            source="upload" if source == "portal" else source,
            consent_id=consent_id,
            content_hash=chash,
            extra=extra,
            conn=conn,
        )
        if doc_id is None:  # lost a race on the same bytes
            row = uploads_repo.find_by_hash(chash, conn=conn)
            return _dup(row) if row else _fail("internal_error")
        return UploadResult(str(doc_id), "received", False, None)
