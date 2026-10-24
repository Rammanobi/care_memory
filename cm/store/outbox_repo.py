"""Lane A: outbox. Rows are written ONLY inside the decision transaction (cm.review.decide)."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from cm.core.db import transaction


def enqueue(row: dict[str, Any], *, conn: Any) -> UUID | None:
    """Upsert on dedup_key. `conn` is required on purpose: callers must be inside the decision
    transaction. Returns outbox_id (the existing id on conflict)."""
    if not (row.get("approval_id") and row.get("decision_id")) and not row.get("template_id"):
        raise ValueError("outbox rows need approval_id + decision_id, or an approved template_id")
    body = row.get("body")
    got = conn.execute(
        "INSERT INTO cm.outbox (outbox_id, kind, recipient_id, channel, body, body_sha256, approval_id, decision_id, "
        "template_id, next_attempt_at, for_date, meta, dedup_key, created_at) "
        "VALUES (COALESCE(%s, gen_random_uuid()),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (dedup_key) DO NOTHING RETURNING outbox_id",
        (
            row.get("outbox_id"),
            row["kind"],
            row["recipient_id"],
            row["channel"],
            body,
            hashlib.sha256(body.encode()).digest() if body else None,
            row.get("approval_id"),
            row.get("decision_id"),
            row.get("template_id"),
            row["next_attempt_at"],
            row.get("for_date"),
            Jsonb(row.get("meta", {})),
            row["dedup_key"],
            row.get("created_at", row["next_attempt_at"]),
        ),
    ).fetchone()
    if got:
        return got["outbox_id"]
    ex = conn.execute(
        "SELECT outbox_id FROM cm.outbox WHERE dedup_key=%s", (row["dedup_key"],)
    ).fetchone()
    return ex["outbox_id"] if ex else None


def for_approval(approval_id: UUID, as_of: datetime, *, conn: Any = None) -> list[dict[str, Any]]:
    if conn is None:
        with transaction() as c:
            return for_approval(approval_id, as_of, conn=c)
    return conn.execute(
        "SELECT * FROM cm.outbox WHERE approval_id=%s AND created_at <= %s ORDER BY created_at",
        (approval_id, as_of),
    ).fetchall()


def inbox_for(
    recipient_id: UUID,
    as_of: datetime,
    *,
    channels: tuple[str, ...] = ("telegram", "web_inbox", "webpush"),
    limit: int = 100,
    include_requests: bool = False,
    conn: Any = None,
) -> list[dict[str, Any]]:
    """Approved messages addressed to a person, newest first (request replies only when asked)."""
    if conn is None:
        with transaction() as c:
            return inbox_for(
                recipient_id,
                as_of,
                channels=channels,
                limit=limit,
                include_requests=include_requests,
                conn=c,
            )
    return conn.execute(
        "SELECT o.*, a.payload->>'title' AS title, a.payload->>'audience' AS audience "
        "FROM cm.outbox o JOIN cm.approvals a ON a.approval_id=o.approval_id "
        "WHERE o.recipient_id=%s AND o.channel = ANY(%s) AND o.created_at <= %s AND o.body IS NOT NULL "
        + (
            ""
            if include_requests
            else "AND COALESCE(a.payload->>'subkind','') <> 'patient_request' "
        )
        + "ORDER BY o.created_at DESC, o.outbox_id LIMIT %s",
        (recipient_id, list(channels), as_of, limit),
    ).fetchall()


def claim_batch(limit: int, *, conn: Any) -> list[dict[str, Any]]:
    """Claim pending rows (FOR UPDATE SKIP LOCKED). Sending is the router's job (not in this slice)."""
    return conn.execute(
        "SELECT * FROM cm.outbox WHERE status='pending' AND next_attempt_at <= now() "
        "ORDER BY next_attempt_at LIMIT %s FOR UPDATE SKIP LOCKED",
        (limit,),
    ).fetchall()


# ---- drainer / sender support (integration slice) -------------------------------------------
_MARKABLE = {
    "provider_message_id": "provider_message_id",
    "sent_at": "sent_at",
    "next_attempt_at": "next_attempt_at",
    "error": "last_error",
    "last_error": "last_error",
}


def get(outbox_id: UUID, *, conn: Any = None) -> dict[str, Any] | None:
    if conn is None:
        with transaction() as c:
            return get(outbox_id, conn=c)
    return conn.execute("SELECT * FROM cm.outbox WHERE outbox_id=%s", (outbox_id,)).fetchone()


def mark(outbox_id: UUID, status: str, *, conn: Any = None, **fields: Any) -> None:
    """Set a final or pending status; always releases the drainer lock. Unknown fields are ignored."""
    if conn is None:
        with transaction() as c:
            return mark(outbox_id, status, conn=c, **fields)
    sets, args = ["status=%s", "locked_by=NULL", "locked_at=NULL"], [status]
    for k, col in _MARKABLE.items():
        if k in fields:
            sets.append(f"{col}=%s")
            args.append(fields[k])
    args.append(outbox_id)
    conn.execute(f"UPDATE cm.outbox SET {', '.join(sets)} WHERE outbox_id=%s", args)  # noqa: S608


def already_sent(dedup_key: str, *, conn: Any = None) -> bool:
    if conn is None:
        with transaction() as c:
            return already_sent(dedup_key, conn=c)
    return (
        conn.execute(
            "SELECT 1 FROM cm.outbox WHERE dedup_key=%s AND status='sent'", (dedup_key,)
        ).fetchone()
        is not None
    )


def sent_today(recipient_id: UUID, day: date, *, conn: Any = None) -> int:
    if conn is None:
        with transaction() as c:
            return sent_today(recipient_id, day, conn=c)
    row = conn.execute(
        "SELECT count(*) AS n FROM cm.outbox WHERE recipient_id=%s AND status='sent' "
        "AND channel='telegram' AND (sent_at AT TIME ZONE 'Asia/Kolkata')::date = %s",
        (recipient_id, day),
    ).fetchone()
    return int(row["n"])


def claim_for_send(
    limit: int, worker: str, at: datetime, *, channel: str = "telegram", stale_s: int = 300
) -> list[dict[str, Any]]:
    """Claim due pending rows in ONE short transaction (SKIP LOCKED), mark them 'sending', commit.

    Rows stuck in 'sending' longer than ``stale_s`` (a crashed drainer) are released first.
    """
    with transaction() as conn:
        conn.execute(
            "UPDATE cm.outbox SET status='pending', locked_by=NULL, locked_at=NULL "
            "WHERE status='sending' AND locked_at < %s - make_interval(secs => %s)",
            (at, stale_s),
        )
        rows = conn.execute(
            "SELECT outbox_id FROM cm.outbox WHERE status='pending' AND channel=%s "
            "AND next_attempt_at <= %s ORDER BY next_attempt_at, created_at LIMIT %s "
            "FOR UPDATE SKIP LOCKED",
            (channel, at, limit),
        ).fetchall()
        ids = [r["outbox_id"] for r in rows]
        if not ids:
            return []
        return conn.execute(
            "UPDATE cm.outbox SET status='sending', locked_by=%s, locked_at=%s, attempts=attempts+1 "
            "WHERE outbox_id = ANY(%s) RETURNING *",
            (worker, at, ids),
        ).fetchall()
