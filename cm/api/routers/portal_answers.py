"""Lane G: GET /portal/answers, instant code-computed answers about the patient's own record.

Patient role only; the patient comes from the session. Supporters do not get this (their view is limited to
the week strip under the patient's sharing consent). No model call, no advice. Logic: cm/api/own_data.py.
"""
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from cm.api.deps import User, now, require_roles
from cm.api.own_data import build_answers
from cm.api.portal_models import AnswerCard
from cm.api.routers.portal import _my_patient
from cm.api.suppress import find_banned
from cm.core.db import transaction
from cm.store import events_repo

router = APIRouter(prefix="/portal", tags=["portal"])


def _summary_of(notes: list[dict[str, Any]]) -> dict[str, Any]:
    for n in notes:
        if n["payload"].get("kind") == "summary":
            return n["payload"]
    return {}


@router.get("/answers", response_model=list[AnswerCard])
def portal_answers(user: User = Depends(require_roles("patient"))) -> list[AnswerCard]:
    at = now()
    with transaction() as conn:
        p = _my_patient(conn, user)
        events = events_repo.query(p["patient_id"], at, types=["DoseCheckin", "Dispense"], conn=conn)
        notes = events_repo.query(p["patient_id"], at, types=["ContextNote"], conn=conn)
        row = conn.execute(
            "SELECT COALESCE(lang,'en') AS lang FROM cm.identity_vault WHERE person_id=%s",
            (user.person_id,),
        ).fetchone()
    appts = [
        n["payload"]
        for n in sorted(notes, key=lambda x: x["payload"].get("order", 0))
        if n["payload"].get("kind") == "appointment"
    ]
    cards = build_answers(events, _summary_of(notes), appts, at, (row or {}).get("lang", "en"), p.get("treatment_start"))
    return [
        AnswerCard(**c)
        for c in cards
        if not find_banned(f"{c['question']} {c['answer_text']}")  # withheld, never rewritten
    ]
