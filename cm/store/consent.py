"""Lane A: consent ledger (append-only). Effective consent is the latest row per (source, purpose)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from cm.core.db import transaction


def consent_state(
    person_id: UUID, as_of: datetime, *, conn: Any = None
) -> dict[str, dict[str, str]]:
    """{source: {purpose: 'granted'|'withdrawn'}} as of a moment. Missing = never."""
    if conn is None:
        with transaction() as c:
            return consent_state(person_id, as_of, conn=c)
    rows = conn.execute(
        "SELECT DISTINCT ON (source, purpose) source, purpose, state FROM cm.consents "
        "WHERE person_id = %s AND effective_at <= %s "
        "ORDER BY source, purpose, effective_at DESC, recorded_at DESC",
        (person_id, as_of),
    ).fetchall()
    out: dict[str, dict[str, str]] = {}
    for r in rows:
        out.setdefault(r["source"], {})[r["purpose"]] = r["state"]
    return out


def has_consent(person_id: UUID, source: str, as_of: datetime, *, conn: Any = None) -> bool:
    st = consent_state(person_id, as_of, conn=conn).get(source, {})
    return any(v == "granted" for v in st.values())


def record_consent(
    person_id: UUID,
    source: str,
    purpose: str,
    state: str,
    effective_at: datetime,
    via: str,
    *,
    notice_version: str = "v1",
    conn: Any = None,
) -> UUID:
    if conn is None:
        with transaction() as c:
            return record_consent(
                person_id,
                source,
                purpose,
                state,
                effective_at,
                via,
                notice_version=notice_version,
                conn=c,
            )
    row = conn.execute(
        "INSERT INTO cm.consents (person_id, source, purpose, state, effective_at, via, notice_version) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING consent_id",
        (person_id, source, purpose, state, effective_at, via, notice_version),
    ).fetchone()
    return row["consent_id"]


def latest_consent_id(person_id: UUID, source: str, as_of: datetime, *, conn: Any) -> UUID | None:
    row = conn.execute(
        "SELECT consent_id FROM cm.consents WHERE person_id=%s AND source=%s AND state='granted' "
        "AND effective_at <= %s ORDER BY effective_at DESC LIMIT 1",
        (person_id, source, as_of),
    ).fetchone()
    return row["consent_id"] if row else None
