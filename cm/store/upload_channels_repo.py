"""Lookups the upload channels (Telegram, Gmail) need. A new file so lane A's repos stay untouched."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from cm.core.db import transaction


def person_token(person_id: UUID, *, conn: Any = None) -> str | None:
    """The pseudonymous person token ('P-0142') of a person, or None."""
    if conn is None:
        with transaction() as c:
            return person_token(person_id, conn=c)
    r = conn.execute("SELECT token FROM cm.persons WHERE person_id=%s", (person_id,)).fetchone()
    return r["token"] if r else None


def doctor_person_by_email(email: str, *, conn: Any = None) -> UUID | None:
    """The doctor person whose vault email equals ``email`` (case-insensitive), or None.

    The demo vault stores the UTF-8 bytes at rest (see channels_repo.first_name_from_vault); rows whose
    bytes are not UTF-8 never match."""
    if conn is None:
        with transaction() as c:
            return doctor_person_by_email(email, conn=c)
    rows = conn.execute(
        "SELECT p.person_id, iv.enc_email FROM cm.persons p JOIN cm.identity_vault iv USING (person_id) "
        "WHERE p.role='doctor'"
    ).fetchall()
    want = email.strip().lower()
    for r in rows:
        try:
            have = bytes(r["enc_email"]).decode("utf-8").strip().lower()
        except (UnicodeDecodeError, TypeError):
            continue
        if have == want:
            return r["person_id"]
    return None
