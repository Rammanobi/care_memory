"""Lane A: bitemporal event store. Idempotent append, bulk append, and the as_of read path."""
# ruff: noqa: S608  (SQL is assembled from fixed fragments; every value is a bound parameter)

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from cm.core.db import transaction


@dataclass(frozen=True)
class NewEvent:
    patient_id: UUID
    type: str
    occurred_at: datetime
    recorded_at: datetime
    source: str
    idempotency_key: str
    reporter_mode: str = "record"
    reporter_id: UUID | None = None
    channel: str | None = None
    consent_id: UUID | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    supersedes: UUID | None = None
    event_id: UUID | None = None


_INSERT = """
INSERT INTO cm.events (event_id, patient_id, type, occurred_at, recorded_at, source, reporter_id, reporter_mode,
                       channel, consent_id, payload, supersedes, idempotency_key)
VALUES (COALESCE(%s, gen_random_uuid()),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING event_id
"""


def _params(e: NewEvent) -> tuple[Any, ...]:
    return (
        e.event_id,
        e.patient_id,
        e.type,
        e.occurred_at,
        e.recorded_at,
        e.source,
        e.reporter_id,
        e.reporter_mode,
        e.channel,
        e.consent_id,
        Jsonb(e.payload),
        e.supersedes,
        e.idempotency_key,
    )


def append_event(event: NewEvent, *, conn: Any = None) -> tuple[UUID, bool]:
    """Insert once per idempotency_key. Returns (event_id, created)."""
    if conn is None:
        with transaction() as c:
            return append_event(event, conn=c)
    row = conn.execute(_INSERT, _params(event)).fetchone()
    if row:
        return row["event_id"], True
    existing = conn.execute(
        "SELECT event_id FROM cm.events WHERE idempotency_key = %s", (event.idempotency_key,)
    ).fetchone()
    return existing["event_id"], False


def bulk_append(events: Iterable[NewEvent], *, conn: Any = None) -> int:
    """Append many events; returns how many were newly created."""
    if conn is None:
        with transaction() as c:
            return bulk_append(events, conn=c)
    created = 0
    for e in events:
        if conn.execute(_INSERT, _params(e)).fetchone():
            created += 1
    return created


def query(
    patient_id: UUID,
    as_of: datetime,
    recorded_as_of: datetime | None = None,
    *,
    types: list[str] | None = None,
    limit: int | None = None,
    conn: Any = None,
) -> list[dict[str, Any]]:
    """Events a reader could know at `as_of`: occurred_at <= as_of and recorded_at <= recorded_as_of."""
    if conn is None:
        with transaction() as c:
            return query(patient_id, as_of, recorded_as_of, types=types, limit=limit, conn=c)
    sql = (
        "SELECT * FROM cm.events WHERE patient_id = %s AND occurred_at <= %s AND recorded_at <= %s"
        + (" AND type = ANY(%s)" if types else "")
        + " ORDER BY occurred_at DESC, event_id"
        + (" LIMIT %s" if limit else "")
    )
    args: list[Any] = [patient_id, as_of, recorded_as_of or as_of]
    if types:
        args.append(types)
    if limit:
        args.append(limit)
    return conn.execute(sql, args).fetchall()


def missed_days(patient_id: UUID, since: datetime, until: datetime, *, conn: Any = None) -> int:
    """Distinct for_date values with a 'missed' DoseCheckin in [since, until]."""
    if conn is None:
        with transaction() as c:
            return missed_days(patient_id, since, until, conn=c)
    row = conn.execute(
        "SELECT count(DISTINCT payload->>'for_date') AS n FROM cm.events WHERE patient_id=%s "
        "AND type='DoseCheckin' AND payload->>'status'='missed' AND occurred_at >= %s AND occurred_at <= %s",
        (patient_id, since, until),
    ).fetchone()
    return int(row["n"])
