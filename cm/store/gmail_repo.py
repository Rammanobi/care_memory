"""Lane M integration slice: SQL for Gmail reply tokens, mailbox cursor / watch state and message dedup.

Kept in cm/store because raw SQL is not allowed elsewhere. Same style as channels_repo (``conn`` optional).
Message dedup uses cm.audit_log rows (action ``gmail_msg_processed``, id in ``result_ids``) because no
dedicated table exists; the lookup is bounded to a window that covers the 2-day recent-list fallback.
"""
# ruff: noqa: S608

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from cm.core.db import transaction

PROCESSED_ACTION = "gmail_msg_processed"
DEDUP_WINDOW = timedelta(days=4)


def _h(token_hash_hex: str) -> bytes:
    return bytes.fromhex(token_hash_hex)


# ---------------------------------------------------------------- approval_tokens
def mint_tokens(rows: list[tuple[str, UUID]], doctor_id: UUID, expires_at: datetime, *, conn: Any = None) -> None:
    if conn is None:
        with transaction() as c:
            return mint_tokens(rows, doctor_id, expires_at, conn=c)
    for th, approval_id in rows:
        conn.execute(
            "INSERT INTO cm.approval_tokens (token_hash, approval_id, doctor_id, expires_at) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT (token_hash) DO NOTHING",
            (_h(th), approval_id, doctor_id, expires_at),
        )


def consume_token(
    token_hash_hex: str, doctor_id: UUID, now: datetime, *, conn: Any = None
) -> tuple[str, UUID | None]:
    """Atomic single-use consume. Returns (status, approval_id)."""
    if conn is None:
        with transaction() as c:
            return consume_token(token_hash_hex, doctor_id, now, conn=c)
    th = _h(token_hash_hex)
    got = conn.execute(
        "UPDATE cm.approval_tokens SET used_at=%s WHERE token_hash=%s AND doctor_id=%s "
        "AND used_at IS NULL AND expires_at > %s RETURNING approval_id",
        (now, th, doctor_id, now),
    ).fetchone()
    if got:
        return "ok", got["approval_id"]
    row = conn.execute(
        "SELECT doctor_id, used_at, expires_at FROM cm.approval_tokens WHERE token_hash=%s", (th,)
    ).fetchone()
    if row is None:
        return "unknown", None
    if row["doctor_id"] != doctor_id:
        return "wrong_doctor", None
    if row["used_at"] is not None:
        return "used", None
    return "expired", None


def release_token(token_hash_hex: str, *, conn: Any = None) -> None:
    if conn is None:
        with transaction() as c:
            return release_token(token_hash_hex, conn=c)
    conn.execute("UPDATE cm.approval_tokens SET used_at=NULL WHERE token_hash=%s", (_h(token_hash_hex),))


# ---------------------------------------------------------------- gmail_state
def get_cursor(mailbox: str, *, conn: Any = None) -> int | None:
    if conn is None:
        with transaction() as c:
            return get_cursor(mailbox, conn=c)
    r = conn.execute("SELECT history_id FROM cm.gmail_state WHERE mailbox=%s", (mailbox,)).fetchone()
    return int(r["history_id"]) if r and r["history_id"] is not None else None


def advance_cursor(mailbox: str, history_id: int, *, conn: Any = None) -> int:
    """GREATEST(old, new); returns the stored value."""
    if conn is None:
        with transaction() as c:
            return advance_cursor(mailbox, history_id, conn=c)
    r = conn.execute(
        "INSERT INTO cm.gmail_state (mailbox, history_id) VALUES (%s,%s) "
        "ON CONFLICT (mailbox) DO UPDATE SET history_id=GREATEST(COALESCE(cm.gmail_state.history_id,0), EXCLUDED.history_id) "
        "RETURNING history_id",
        (mailbox, history_id),
    ).fetchone()
    return int(r["history_id"])


def get_watch_expiry_ms(mailbox: str, *, conn: Any = None) -> int | None:
    if conn is None:
        with transaction() as c:
            return get_watch_expiry_ms(mailbox, conn=c)
    r = conn.execute("SELECT watch_expiration FROM cm.gmail_state WHERE mailbox=%s", (mailbox,)).fetchone()
    if not r or r["watch_expiration"] is None:
        return None
    return int(r["watch_expiration"].timestamp() * 1000)


def set_watch(mailbox: str, history_id: int, expiration_ms: int, *, conn: Any = None) -> None:
    if conn is None:
        with transaction() as c:
            return set_watch(mailbox, history_id, expiration_ms, conn=c)
    exp = datetime.fromtimestamp(expiration_ms / 1000, tz=UTC)
    conn.execute(
        "INSERT INTO cm.gmail_state (mailbox, history_id, watch_expiration) VALUES (%s,%s,%s) "
        "ON CONFLICT (mailbox) DO UPDATE SET watch_expiration=EXCLUDED.watch_expiration, "
        "history_id=GREATEST(COALESCE(cm.gmail_state.history_id,0), EXCLUDED.history_id)",
        (mailbox, history_id, exp),
    )


# ---------------------------------------------------------------- message dedup (audit_log backed)
def is_processed(message_id: str, now: datetime, *, conn: Any = None) -> bool:
    if conn is None:
        with transaction() as c:
            return is_processed(message_id, now, conn=c)
    r = conn.execute(
        "SELECT 1 FROM cm.audit_log WHERE action=%s AND at > %s AND %s = ANY(result_ids) LIMIT 1",
        (PROCESSED_ACTION, now - DEDUP_WINDOW, message_id),
    ).fetchone()
    return r is not None


def mark_processed(message_id: str, now: datetime, *, conn: Any = None) -> None:
    if conn is None:
        with transaction() as c:
            return mark_processed(message_id, now, conn=c)
    digest = hashlib.sha256(message_id.encode()).hexdigest()
    conn.execute(
        "INSERT INTO cm.audit_log (at, actor, role, action, tool, args_hash, result_ids) "
        "VALUES (%s,'system','system',%s,'gmail',%s,%s)",
        (now, PROCESSED_ACTION, digest, [message_id]),
    )


# ---------------------------------------------------------------- doctor lookup + approved visits (calendar sync)
def approved_visit_decisions(as_of: datetime, *, conn: Any = None) -> list[dict[str, Any]]:
    """Approved/edited visit_list approvals decided at or before as_of: approval_id, patient_id, payload."""
    if conn is None:
        with transaction() as c:
            return approved_visit_decisions(as_of, conn=c)
    return conn.execute(
        "SELECT a.approval_id, a.patient_id, a.payload FROM cm.approvals a "
        "JOIN cm.review_decisions d ON d.approval_id=a.approval_id "
        "WHERE a.kind='visit_list' AND a.status IN ('approved','edited') AND d.decided_at <= %s "
        "ORDER BY d.decided_at",
        (as_of,),
    ).fetchall()


def approval_tier(approval_id: UUID, *, conn: Any = None) -> str | None:
    """Current tier of an approval (None when unknown); used to keep Red console-only."""
    if conn is None:
        with transaction() as c:
            return approval_tier(approval_id, conn=c)
    r = conn.execute("SELECT tier FROM cm.approvals WHERE approval_id=%s", (approval_id,)).fetchone()
    return r["tier"] if r else None
