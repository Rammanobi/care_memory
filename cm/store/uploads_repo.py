"""Lane A: persistence for uploaded documents (cm.documents rows carrying extra.upload_state). All upload SQL.

Lifecycle lives in ``extra.upload_state`` (cm.documents.status only allows active/superseded/withdrawn):
received -> extracting -> pending_review -> accepted | rejected | failed.
"""
# ruff: noqa: S608  (_COLS is a module constant, never user input)

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from cm.core.db import transaction

UPLOAD_DOC_TYPE = (
    "lab"  # placeholder: documents.doc_type is NOT NULL; the real type is set on review
)
_COLS = (
    "document_id, patient_token, doc_type, source, recorded_at, consent_id, content_hash, gcs_uri, "
    "status, extra"
)


def insert(
    *,
    patient_token: str,
    source: str,
    consent_id: UUID | None,
    content_hash: bytes,
    extra: dict[str, Any],
    conn: Any = None,
) -> UUID | None:
    """Insert a received upload; None when the content_hash already exists (lost a dedupe race)."""
    if conn is None:
        with transaction() as c:
            return insert(
                patient_token=patient_token,
                source=source,
                consent_id=consent_id,
                content_hash=content_hash,
                extra=extra,
                conn=c,
            )
    row = conn.execute(
        "INSERT INTO cm.documents (patient_token, doc_type, source, author_role, consent_id, content_hash, extra) "
        "VALUES (%s,%s,%s,'patient',%s,%s,%s) ON CONFLICT (content_hash) DO NOTHING RETURNING document_id",
        (
            patient_token,
            UPLOAD_DOC_TYPE,
            source,
            consent_id,
            content_hash,
            Jsonb({"upload_state": "received", **extra}),
        ),
    ).fetchone()
    return row["document_id"] if row else None


def lock_patient(patient_token: str, *, conn: Any) -> None:
    """Serialise one patient's uploads until the transaction ends (rate limit and dedupe stay exact under races)."""
    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("cm.upload:" + patient_token,)
    )


def get(document_id: UUID, *, conn: Any = None) -> dict[str, Any] | None:
    if conn is None:
        with transaction() as c:
            return get(document_id, conn=c)
    return conn.execute(
        f"SELECT {_COLS} FROM cm.documents WHERE document_id=%s AND extra ? 'upload_state'",
        (document_id,),
    ).fetchone()


def find_by_hash(content_hash: bytes, *, conn: Any = None) -> dict[str, Any] | None:
    if conn is None:
        with transaction() as c:
            return find_by_hash(content_hash, conn=c)
    return conn.execute(
        f"SELECT {_COLS} FROM cm.documents WHERE content_hash=%s", (content_hash,)
    ).fetchone()


def find_by_origin(
    patient_token: str, origin_key: str, *, conn: Any = None
) -> dict[str, Any] | None:
    if conn is None:
        with transaction() as c:
            return find_by_origin(patient_token, origin_key, conn=c)
    return conn.execute(
        f"SELECT {_COLS} FROM cm.documents WHERE patient_token=%s AND extra->>'origin_key'=%s LIMIT 1",
        (patient_token, origin_key),
    ).fetchone()


def set_state(
    document_id: UUID, state: str, detail: dict[str, Any] | None = None, *, conn: Any = None
) -> bool:
    """Move an upload to ``state`` (merging ``detail`` into extra). False when no such upload."""
    if conn is None:
        with transaction() as c:
            return set_state(document_id, state, detail, conn=c)
    row = conn.execute(
        "UPDATE cm.documents SET extra = extra || %s WHERE document_id=%s AND extra ? 'upload_state' "
        "RETURNING document_id",
        (Jsonb({**(detail or {}), "upload_state": state}), document_id),
    ).fetchone()
    return row is not None


def list_for_patient(
    patient_token: str, *, as_of: datetime | None = None, conn: Any = None
) -> list[dict[str, Any]]:
    """Uploads of one patient, newest first. ``as_of`` (rule 9) hides rows recorded after it; None = all.

    recorded_at is database wall time, so callers on a pinned demo clock should leave ``as_of`` None.
    """
    if conn is None:
        with transaction() as c:
            return list_for_patient(patient_token, as_of=as_of, conn=c)
    return conn.execute(
        f"SELECT {_COLS} FROM cm.documents WHERE patient_token=%s AND extra ? 'upload_state' "
        "AND (%s::timestamptz IS NULL OR recorded_at <= %s) ORDER BY recorded_at DESC",
        (patient_token, as_of, as_of),
    ).fetchall()


def count_recent(patient_token: str, seconds: int = 3600, *, conn: Any = None) -> int:
    """Uploads recorded in the last ``seconds`` of WALL time (database now(), not the demo clock).

    Deliberately no ``as_of``: this is the abuse rate limit, and recorded_at is stamped by the database.
    """
    if conn is None:
        with transaction() as c:
            return count_recent(patient_token, seconds, conn=c)
    return conn.execute(
        "SELECT count(*) AS n FROM cm.documents WHERE patient_token=%s AND extra ? 'upload_state' "
        "AND recorded_at > now() - make_interval(secs => %s)",
        (patient_token, seconds),
    ).fetchone()["n"]
