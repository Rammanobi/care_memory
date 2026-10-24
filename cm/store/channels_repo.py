"""Integration slice: SQL for Telegram bindings, audit writes, template lookup and reminder candidates.

Kept in cm/store because raw SQL is not allowed elsewhere. ``binding_id`` is the person_id: the table's
primary key is (person_id, channel).
"""
# ruff: noqa: S608

from __future__ import annotations

import hashlib
import json
import secrets
import unicodedata
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from cm.core.db import transaction

_B = (
    "SELECT cb.person_id, cb.external_id, cb.invite_code, cb.invite_expires_at, cb.status, p.role, "
    "pt.patient_id, COALESCE(iv.lang,'en') AS lang FROM cm.channel_bindings cb "
    "JOIN cm.persons p USING (person_id) LEFT JOIN cm.patients pt ON pt.person_id=cb.person_id "
    "LEFT JOIN cm.identity_vault iv ON iv.person_id=cb.person_id WHERE cb.channel='telegram' "
)


def binding_by_chat(chat_id: str, *, conn: Any = None) -> dict[str, Any] | None:
    if conn is None:
        with transaction() as c:
            return binding_by_chat(chat_id, conn=c)
    return conn.execute(
        _B
        + "AND cb.external_id=%s ORDER BY (cb.status='active') DESC, cb.bound_at DESC NULLS LAST LIMIT 1",
        (chat_id,),
    ).fetchone()


def binding_by_invite(code: str, *, conn: Any = None) -> dict[str, Any] | None:
    if conn is None:
        with transaction() as c:
            return binding_by_invite(code, conn=c)
    return conn.execute(_B + "AND cb.invite_code=%s AND cb.status='pending'", (code,)).fetchone()


def binding_by_person(person_id: UUID, *, conn: Any = None) -> dict[str, Any] | None:
    if conn is None:
        with transaction() as c:
            return binding_by_person(person_id, conn=c)
    return conn.execute(_B + "AND cb.person_id=%s", (person_id,)).fetchone()


def activate_binding(person_id: UUID, chat_id: str, at: datetime, *, conn: Any = None) -> None:
    if conn is None:
        with transaction() as c:
            return activate_binding(person_id, chat_id, at, conn=c)
    conn.execute(  # a chat belongs to one person: free it from any earlier binding
        "UPDATE cm.channel_bindings SET status='revoked' WHERE channel='telegram' AND external_id=%s "
        "AND person_id<>%s AND status IN ('active','blocked')",
        (chat_id, person_id),
    )
    conn.execute(
        "UPDATE cm.channel_bindings SET status='active', external_id=%s, bound_at=%s, invite_code=NULL, "
        "invite_expires_at=NULL WHERE person_id=%s AND channel='telegram'",
        (chat_id, at, person_id),
    )


def set_binding_status(person_id: UUID, status: str, *, conn: Any = None) -> None:
    if conn is None:
        with transaction() as c:
            return set_binding_status(person_id, status, conn=c)
    conn.execute(
        "UPDATE cm.channel_bindings SET status=%s WHERE person_id=%s AND channel='telegram'",
        (status, person_id),
    )


def create_invite(person_id: UUID, at: datetime, ttl_hours: int = 24, *, conn: Any = None) -> str:
    """One-time /start code (single use, expiring). Resets the binding to pending."""
    if conn is None:
        with transaction() as c:
            return create_invite(person_id, at, ttl_hours, conn=c)
    code = secrets.token_urlsafe(9).replace("-", "x").replace("_", "y")
    conn.execute(
        "INSERT INTO cm.channel_bindings (person_id, channel, status, invite_code, invite_expires_at) "
        "VALUES (%s,'telegram','pending',%s,%s) ON CONFLICT (person_id, channel) DO UPDATE SET "
        "status='pending', external_id=NULL, bound_at=NULL, invite_code=EXCLUDED.invite_code, "
        "invite_expires_at=EXCLUDED.invite_expires_at",
        (person_id, code, at + timedelta(hours=ttl_hours)),
    )
    return code


def person_by_token(token: str, *, conn: Any = None) -> dict[str, Any] | None:
    if conn is None:
        with transaction() as c:
            return person_by_token(token, conn=c)
    return conn.execute(
        "SELECT p.person_id, p.role, pt.patient_id FROM cm.persons p "
        "LEFT JOIN cm.patients pt USING (person_id) WHERE p.token=%s",
        (token,),
    ).fetchone()


def patient_person(patient_id: UUID, *, conn: Any = None) -> UUID | None:
    if conn is None:
        with transaction() as c:
            return patient_person(patient_id, conn=c)
    r = conn.execute(
        "SELECT person_id FROM cm.patients WHERE patient_id=%s", (patient_id,)
    ).fetchone()
    return r["person_id"] if r else None


def write_audit(action: str, fields: dict[str, Any], at: datetime, *, conn: Any = None) -> None:
    if conn is None:
        with transaction() as c:
            return write_audit(action, fields, at, conn=c)
    digest = hashlib.sha256(json.dumps(fields, sort_keys=True, default=str).encode()).hexdigest()
    ids = [str(fields[k]) for k in ("outbox_id", "person_id") if fields.get(k)]
    conn.execute(
        "INSERT INTO cm.audit_log (at, actor, role, action, tool, args_hash, result_ids) "
        "VALUES (%s,'system','system',%s,'telegram',%s,%s)",
        (at, action, digest, ids),
    )


def approved_template(key: str, lang: str = "en", *, conn: Any = None) -> dict[str, Any] | None:
    if conn is None:
        with transaction() as c:
            return approved_template(key, lang, conn=c)
    return conn.execute(
        "SELECT * FROM cm.templates WHERE key=%s AND lang=%s AND status='approved'", (key, lang)
    ).fetchone()


def ensure_template(
    key: str, lang: str, body: str, slots: list[str], at: datetime, *, conn: Any = None
) -> UUID | None:
    """Return the approved template id; create it (approved by the first doctor) from the YAML when absent."""
    if conn is None:
        with transaction() as c:
            return ensure_template(key, lang, body, slots, at, conn=c)
    ex = approved_template(key, lang, conn=conn)
    if ex:
        return ex["template_id"]
    doc = conn.execute(
        "SELECT person_id FROM cm.persons WHERE role='doctor' ORDER BY token LIMIT 1"
    ).fetchone()
    if not doc:
        return None
    return conn.execute(
        "INSERT INTO cm.templates (key, lang, body, slots, tier, status, approved_by, approved_at) "
        "VALUES (%s,%s,%s,%s,'green','approved',%s,%s) ON CONFLICT DO NOTHING RETURNING template_id",
        (key, lang, body, slots, doc["person_id"], at),
    ).fetchone()["template_id"]


_NAME_CHARS = {"L", "M"}  # letters and combining marks (Telugu vowel signs are marks)


def first_name_from_vault(raw: Any) -> str | None:
    """Decrypt a vault ``enc_name`` value to a safe first name, or None.

    Same approved path as ``cm.api.deps.display_name_of`` (the vault holds the UTF-8 name bytes at rest in
    the demo; swap to ``cm.core.crypto.decrypt_field`` here when the DEK path lands). Only the first word is
    returned, letters only, so no other vault field and no free text can reach a patient message.
    """
    if not raw:
        return None
    try:
        text = bytes(raw).decode("utf-8")
    except (UnicodeDecodeError, TypeError):
        return None
    for prefix in ("Dr.", "Dr", "Mr.", "Mrs.", "Ms."):
        if text.startswith(prefix + " "):
            text = text[len(prefix) :].lstrip()
    for word in text.split():
        name = "".join(ch for ch in word if unicodedata.category(ch)[0] in _NAME_CHARS)
        if name:
            return name[:40]
    return None


def person_first_name(person_id: UUID, *, conn: Any = None) -> str | None:
    if conn is None:
        with transaction() as c:
            return person_first_name(person_id, conn=c)
    r = conn.execute("SELECT enc_name FROM cm.identity_vault WHERE person_id=%s", (person_id,)).fetchone()
    return first_name_from_vault(r["enc_name"]) if r else None


def reminder_targets(*, conn: Any = None) -> list[dict[str, Any]]:
    """Active Telegram-bound patients. ``first_name`` is the decrypted first name only (never enc_name)."""
    if conn is None:
        with transaction() as c:
            return reminder_targets(conn=c)
    rows = conn.execute(
        "SELECT cb.person_id, pt.patient_id, COALESCE(iv.lang,'en') AS lang, iv.enc_name "
        "FROM cm.channel_bindings cb "
        "JOIN cm.patients pt ON pt.person_id=cb.person_id "
        "LEFT JOIN cm.identity_vault iv ON iv.person_id=cb.person_id "
        "WHERE cb.channel='telegram' AND cb.status='active' AND pt.status='active'"
    ).fetchall()
    out = []
    for r in rows:
        d = {k: v for k, v in r.items() if k != "enc_name"}
        d["first_name"] = first_name_from_vault(r["enc_name"])
        out.append(d)
    return out
