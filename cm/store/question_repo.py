"""Read-only lookups for the patient-question research agent (new file so other repos stay untouched)."""

from __future__ import annotations

from typing import Any

from cm.core.db import transaction


def patient_context(token: str, *, conn: Any = None) -> dict[str, Any] | None:
    """{patient_id, person_id, lang} for a patient token like 'P-0142', or None. ``lang`` defaults to 'en'.

    Never returns the encrypted name or any contact detail."""
    if conn is None:
        with transaction() as c:
            return patient_context(token, conn=c)
    return conn.execute(
        "SELECT pt.patient_id, p.person_id, COALESCE(iv.lang, 'en') AS lang FROM cm.persons p "
        "JOIN cm.patients pt ON pt.person_id = p.person_id "
        "LEFT JOIN cm.identity_vault iv ON iv.person_id = p.person_id WHERE p.token = %s",
        (token,),
    ).fetchone()
