"""Lane A: persistence for the patient RAG index (cm.documents, cm.text_chunks). The only SQL for chunks.

Every write is an upsert, so rebuilding an index twice leaves identical rows (documents are unique on
``content_hash``, chunks on ``(document_id, content_hash)``).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from cm.core.db import transaction

EMBED_DIM = 1536


def _vec(v: list[float] | None) -> str | None:
    if v is None:
        return None
    if len(v) != EMBED_DIM:
        raise ValueError(f"embedding must have {EMBED_DIM} dimensions, got {len(v)}")
    return "[" + ",".join(f"{x:.6g}" for x in v) + "]"


def upsert_document(doc: dict[str, Any], *, conn: Any = None) -> UUID:
    """Insert a document unless one with the same content_hash exists; return its id either way."""
    if conn is None:
        with transaction() as c:
            return upsert_document(doc, conn=c)
    row = conn.execute(
        "INSERT INTO cm.documents (patient_token, doc_type, source, author_role, occurred_at, recorded_at, "
        "consent_id, language, extraction_model, content_hash, sensitivity, extra) "
        "VALUES (%(patient_token)s,%(doc_type)s,%(source)s,%(author_role)s,%(occurred_at)s,%(recorded_at)s,"
        "%(consent_id)s,%(language)s,%(extraction_model)s,%(content_hash)s,%(sensitivity)s,%(extra)s) "
        "ON CONFLICT (content_hash) DO UPDATE SET content_hash = cm.documents.content_hash "
        "RETURNING document_id",
        {
            "consent_id": None,
            "language": "en",
            "extraction_model": None,
            "sensitivity": "normal",
            **doc,
            "extra": Jsonb(doc.get("extra", {})),
        },
    ).fetchone()
    return row["document_id"]


def embedded_chunk_keys(
    document_ids: Iterable[UUID], *, conn: Any = None
) -> set[tuple[UUID, bytes]]:
    """(document_id, content_hash) of chunks that already have an embedding (skip re-embedding them)."""
    ids = list(document_ids)
    if not ids:
        return set()
    if conn is None:
        with transaction() as c:
            return embedded_chunk_keys(ids, conn=c)
    rows = conn.execute(
        "SELECT document_id, content_hash FROM cm.text_chunks WHERE document_id = ANY(%s) AND embedding IS NOT NULL",
        (ids,),
    ).fetchall()
    return {(r["document_id"], bytes(r["content_hash"])) for r in rows}


def upsert_chunk(chunk: dict[str, Any], *, conn: Any = None) -> tuple[UUID, bool]:
    """Insert a chunk or return the existing one. Returns (chunk_id, inserted).

    An existing chunk without an embedding gains one when the caller supplies it; nothing else is overwritten.
    """
    if conn is None:
        with transaction() as c:
            return upsert_chunk(chunk, conn=c)
    emb = _vec(chunk.get("embedding"))
    model = chunk.get("embedding_model") if emb is not None else None
    row = conn.execute(
        "INSERT INTO cm.text_chunks (document_id, parent_id, patient_token, doc_type, occurred_at, recorded_at, "
        "consent_id, language, sensitivity, content, content_hash, embedding, embedding_model, extra) "
        "VALUES (%(document_id)s,%(parent_id)s,%(patient_token)s,%(doc_type)s,%(occurred_at)s,%(recorded_at)s,"
        "%(consent_id)s,%(language)s,%(sensitivity)s,%(content)s,%(content_hash)s,%(embedding)s,%(model)s,%(extra)s) "
        "ON CONFLICT (document_id, content_hash) DO UPDATE SET "
        "embedding = COALESCE(cm.text_chunks.embedding, EXCLUDED.embedding), "
        "embedding_model = CASE WHEN cm.text_chunks.embedding IS NULL THEN EXCLUDED.embedding_model "
        "ELSE cm.text_chunks.embedding_model END, "
        "parent_id = COALESCE(cm.text_chunks.parent_id, EXCLUDED.parent_id) "
        "RETURNING chunk_id, (xmax = 0) AS inserted",
        {
            "parent_id": None,
            "consent_id": None,
            "language": "en",
            "sensitivity": "normal",
            **chunk,
            "embedding": emb,
            "model": model,
            "extra": Jsonb(chunk.get("extra", {})),
        },
    ).fetchone()
    return row["chunk_id"], bool(row["inserted"])


def list_chunks(
    patient_token: str,
    *,
    kind: str | None = None,
    as_of: datetime | None = None,
    conn: Any = None,
) -> list[dict[str, Any]]:
    """Active chunks of one patient, oldest first; optional kind and bitemporal as_of filter."""
    if conn is None:
        with transaction() as c:
            return list_chunks(patient_token, kind=kind, as_of=as_of, conn=c)
    sql = (
        "SELECT chunk_id, document_id, parent_id, doc_type, occurred_at, recorded_at, content, content_hash, "
        "(embedding IS NOT NULL) AS has_embedding, embedding_model, extra FROM cm.text_chunks "
        "WHERE patient_token = %s AND status = 'active'"
    )
    args: list[Any] = [patient_token]
    if kind:
        sql += " AND extra->>'kind' = %s"
        args.append(kind)
    if as_of is not None:
        sql += " AND occurred_at <= %s AND recorded_at <= %s"
        args += [as_of, as_of]
    return conn.execute(sql + " ORDER BY occurred_at, recorded_at, chunk_id", args).fetchall()


def count_chunks(patient_token: str, *, conn: Any = None) -> int:
    if conn is None:
        with transaction() as c:
            return count_chunks(patient_token, conn=c)
    row = conn.execute(
        "SELECT count(*) AS n FROM cm.text_chunks WHERE patient_token = %s AND status = 'active'",
        (patient_token,),
    ).fetchone()
    return int(row["n"])


def count_documents(patient_token: str, *, conn: Any = None) -> int:
    if conn is None:
        with transaction() as c:
            return count_documents(patient_token, conn=c)
    row = conn.execute(
        "SELECT count(*) AS n FROM cm.documents WHERE patient_token = %s AND status = 'active'",
        (patient_token,),
    ).fetchone()
    return int(row["n"])


def delete_patient_index(patient_token: str, *, conn: Any = None) -> int:
    """Remove a patient's index (documents cascade to chunks). Used by tests and full rebuilds; returns rows."""
    if conn is None:
        with transaction() as c:
            return delete_patient_index(patient_token, conn=c)
    return conn.execute(
        "DELETE FROM cm.documents WHERE patient_token = %s", (patient_token,)
    ).rowcount
