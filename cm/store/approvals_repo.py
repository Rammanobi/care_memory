"""Lane A: approvals = the doctor queue. Reads take as_of (created_at <= as_of)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from cm.core.db import transaction

_BASE = (
    "SELECT a.*, per.token AS patient_token, "
    "jsonb_array_length(a.evidence) AS evidence_count, "
    "COALESCE((SELECT o.status FROM cm.outbox o WHERE o.approval_id=a.approval_id "
    "ORDER BY o.created_at LIMIT 1), 'none') AS delivery "
    "FROM cm.approvals a LEFT JOIN cm.patients p ON p.patient_id=a.patient_id "
    "LEFT JOIN cm.persons per ON per.person_id=p.person_id"
)


def upsert(a: dict[str, Any], *, conn: Any = None) -> UUID:
    """Insert an approval; idempotent on (thread_id, interrupt_id). Returns approval_id."""
    if conn is None:
        with transaction() as c:
            return upsert(a, conn=c)
    row = conn.execute(
        "INSERT INTO cm.approvals (approval_id, patient_id, thread_id, interrupt_id, graph_kind, tier, kind, "
        "payload, evidence, status, redraft_count, sample_reason, created_at, due_at, expires_at) "
        "VALUES (COALESCE(%(approval_id)s, gen_random_uuid()), %(patient_id)s, %(thread_id)s, "
        "%(interrupt_id)s, %(graph_kind)s, %(tier)s, %(kind)s, %(payload)s, %(evidence)s, 'pending', 0, "
        "%(sample_reason)s, %(created_at)s, %(due_at)s, %(expires_at)s) "
        "ON CONFLICT (thread_id, interrupt_id) DO NOTHING RETURNING approval_id",
        {
            "approval_id": a.get("approval_id"),
            "patient_id": a.get("patient_id"),
            "thread_id": a["thread_id"],
            "interrupt_id": a["interrupt_id"],
            "graph_kind": a.get("graph_kind", "deep"),
            "tier": a["tier"],
            "kind": a["kind"],
            "payload": Jsonb(a["payload"]),
            "evidence": Jsonb(a.get("evidence", [])),
            "sample_reason": a.get("sample_reason"),
            "created_at": a["created_at"],
            "due_at": a["due_at"],
            "expires_at": a["expires_at"],
        },
    ).fetchone()
    if row:
        return row["approval_id"]
    ex = conn.execute(
        "SELECT approval_id FROM cm.approvals WHERE thread_id=%s AND interrupt_id=%s",
        (a["thread_id"], a["interrupt_id"]),
    ).fetchone()
    return ex["approval_id"]


def get(approval_id: UUID, as_of: datetime, *, conn: Any = None) -> dict[str, Any] | None:
    if conn is None:
        with transaction() as c:
            return get(approval_id, as_of, conn=c)
    return conn.execute(
        _BASE + " WHERE a.approval_id=%s AND a.created_at <= %s", (approval_id, as_of)
    ).fetchone()


def queue(
    as_of: datetime,
    *,
    status: str | None = "pending",
    tier: str | None = None,
    kind: str | None = None,
    patient_id: UUID | None = None,
    exclude_subkind: str | None = None,
    only_subkind: str | None = None,
    cursor: int = 0,
    limit: int = 50,
    conn: Any = None,
) -> list[dict[str, Any]]:
    """Queue page sorted by time remaining (due_at ascending), Red first on ties."""
    if conn is None:
        with transaction() as c:
            return queue(
                as_of,
                status=status,
                tier=tier,
                kind=kind,
                patient_id=patient_id,
                exclude_subkind=exclude_subkind,
                only_subkind=only_subkind,
                cursor=cursor,
                limit=limit,
                conn=c,
            )
    where, args = ["a.created_at <= %s"], [as_of]
    for col, val in (
        ("a.status", status),
        ("a.tier", tier),
        ("a.kind", kind),
        ("a.patient_id", patient_id),
    ):
        if val is not None:
            where.append(f"{col} = %s")
            args.append(val)
    if exclude_subkind:
        where.append("COALESCE(a.payload->>'subkind','') <> %s")
        args.append(exclude_subkind)
    if only_subkind:
        where.append("a.payload->>'subkind' = %s")
        args.append(only_subkind)
    sql = (
        _BASE
        + " WHERE "
        + " AND ".join(where)
        + " ORDER BY a.due_at ASC, (a.tier = 'red') DESC, a.approval_id LIMIT %s OFFSET %s"
    )
    return conn.execute(sql, [*args, limit, cursor]).fetchall()  # type: ignore[arg-type]


def count_pending_by_tier(as_of: datetime, *, conn: Any = None) -> dict[str, int]:
    """Pending counts per tier for the doctor queue (patient requests excluded)."""
    if conn is None:
        with transaction() as c:
            return count_pending_by_tier(as_of, conn=c)
    rows = conn.execute(
        "SELECT tier, count(*) AS n FROM cm.approvals WHERE status='pending' AND created_at <= %s "
        "AND COALESCE(payload->>'subkind','') <> 'patient_request' GROUP BY tier",
        (as_of,),
    ).fetchall()
    return {r["tier"]: r["n"] for r in rows}


_TIER_RANK = {"green": 0, "amber": 1, "red": 2}


def set_research(
    approval_id: UUID,
    research: dict[str, Any],
    *,
    priority: str | None = None,
    tier: str | None = None,
    mark_notified: bool = False,
    conn: Any = None,
) -> dict[str, Any] | None:
    """Write ``payload.data.research`` (and optionally priority / doctor_notified) on a pending question.

    The tier can only go UP (green < amber < red): a Red item is never lowered. Returns the stored
    ``{tier, data}`` or None when the approval does not exist. Only this helper edits ``data.research``.
    """
    if conn is None:
        with transaction() as c:
            return set_research(
                approval_id, research, priority=priority, tier=tier, mark_notified=mark_notified, conn=c
            )
    row = conn.execute(
        "SELECT tier, payload FROM cm.approvals WHERE approval_id=%s FOR UPDATE", (approval_id,)
    ).fetchone()
    if not row:
        return None
    payload = dict(row["payload"])
    data = dict(payload.get("data") or {})
    data["research"] = research
    if priority:
        data["priority"] = priority
    if mark_notified:
        data["doctor_notified"] = True
    payload["data"] = data
    new_tier = row["tier"]
    if tier in _TIER_RANK and _TIER_RANK[tier] > _TIER_RANK[new_tier]:
        new_tier = tier
    conn.execute(
        "UPDATE cm.approvals SET payload=%s, tier=%s WHERE approval_id=%s",
        (Jsonb(payload), new_tier, approval_id),
    )
    return {"tier": new_tier, "data": data}
