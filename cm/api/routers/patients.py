"""Lane G: patient list, detail, timeline, evidence, notes, lens, messages and audit (doctor console)."""
# ruff: noqa: S608  (SQL is assembled from fixed fragments; every value is a bound parameter)
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends

from cm.api import readmodels as rm
from cm.api.deps import (
    ApiError,
    User,
    display_code,
    display_name_of,
    now,
    parse_cursor,
    require_roles,
    resolve_patient,
)
from cm.api.portal_models import (
    AuditRowOut,
    EvidenceOut,
    LensSnapOut,
    MessageOut,
    NoteIn,
    NoteOut,
    PatientDetailOut,
    TimelineEntryOut,
    UiPatient,
)
from cm.api.routers.review import item_from_row
from cm.contracts.api import Page
from cm.core.db import transaction
from cm.core.ids import new_id
from cm.store import approvals_repo, events_repo

router = APIRouter(tags=["patients"])
console = require_roles("doctor", "admin")
Filter = Literal["all", "needs", "requests", "quiet", "visit"]

_KIND = {
    "DoseCheckin": "dose",
    "Dispense": "refill",
    "SupporterVisit": "supporter",
    "LabResult": "lab",
}


@router.get("/patients", response_model=Page[UiPatient])
def list_patients(
    clinic: str | None = None,
    tier: str | None = None,
    q: str | None = None,
    filter: Filter = "all",
    cursor: str | None = None,
    limit: int = 100,
    _: User = Depends(console),
) -> Page[UiPatient]:
    with transaction() as conn:
        rows = rm.ui_patients(conn, now())
    if clinic:
        rows = [p for p in rows if p.clinic == clinic.lower()]
    if tier:
        rows = [p for p in rows if p.level == tier or p.base == tier]
    if q:
        rows = [p for p in rows if q.lower() in p.code.lower() or q.lower() in p.why.lower()]
    keep = {
        "all": lambda p: True,
        "needs": lambda p: p.needs_me,
        "requests": lambda p: p.has_request,
        "quiet": lambda p: p.quiet,
        "visit": lambda p: p.visit_this_week,
    }[filter]
    rows = [p for p in rows if keep(p)]
    start = parse_cursor(cursor)
    limit = max(1, min(limit, 500))
    page = rows[start : start + limit]
    return Page[UiPatient](
        items=page,
        total=len(rows),
        next_cursor=str(start + limit) if start + limit < len(rows) else None,
    )


def _one(conn: Any, key: str, at: Any) -> UiPatient:
    pat = resolve_patient(conn, key)
    for p in rm.ui_patients(conn, at):
        if p.patient_id == pat["patient_id"]:
            return p
    raise ApiError(404, "Patient not found", "not_found")


def _lens(conn: Any, pid: Any, code: str, at: Any) -> list[LensSnapOut]:
    rows = events_repo.query(pid, at, types=["ContextNote"], conn=conn)
    return [
        LensSnapOut.model_validate({**r["payload"]["lens"], "code": code})
        for r in rows
        if r["payload"].get("kind") == "lens"
    ]


@router.get("/patients/{pid}", response_model=PatientDetailOut)
def patient_detail(pid: str, _: User = Depends(console)) -> PatientDetailOut:
    at = now()
    with transaction() as conn:
        p = _one(conn, pid, at)
        pend = approvals_repo.queue(
            at, patient_id=p.patient_id, exclude_subkind="patient_request", conn=conn
        )
        return PatientDetailOut(
            patient=p,
            evidence=rm.evidence_rows(conn, at, p.code),
            notes=rm.notes_for(conn, at, p.code),
            pending_reviews=[item_from_row(r) for r in pend],
            requests=rm.request_rows(conn, at, code=p.code),
            messages=rm.message_rows(conn, at, p.code),
            lens=_lens(conn, p.patient_id, p.code, at),
            as_of=at,
        )


@router.get("/patients/{pid}/timeline", response_model=list[TimelineEntryOut])
def patient_timeline(
    pid: str, day: int | None = None, limit: int = 200, _: User = Depends(console)
) -> list[TimelineEntryOut]:
    at = now()
    with transaction() as conn:
        pat = resolve_patient(conn, pid)
        rows = events_repo.query(pat["patient_id"], at, limit=max(1, min(limit, 500)), conn=conn)
    start = pat["treatment_start"]
    out = []
    for r in rows:
        pl = r["payload"]
        if pl.get("kind") in ("summary", "lens", "appointment"):
            continue
        out.append(
            TimelineEntryOut(
                id=pl.get("ref") or str(r["event_id"]),
                event_id=r["event_id"],
                day=(r["occurred_at"].date() - start).days + 1,
                occurred_at=r["occurred_at"],
                recorded_at=r["recorded_at"],
                type=r["type"],
                kind=pl.get("kind") or _KIND.get(r["type"], "system"),
                source=r["source"],
                text=_timeline_text(r),
                ref=pl.get("ref"),
            )
        )
    return out if day is None else [e for e in out if e.day <= day]


def _timeline_text(r: dict[str, Any]) -> str:
    pl = r["payload"]
    if r["type"] == "ReviewDecisionEvent":
        return f"Doctor decision: {pl.get('action')} ({pl.get('kind')})"
    if r["type"] == "DoseCheckin":
        return f"Dose {pl.get('status')}" + (f", {pl['reason']}" if pl.get("reason") else "")
    return str(pl.get("text") or pl.get("status") or r["type"])


@router.get("/evidence", response_model=list[EvidenceOut])
def evidence_list(code: str | None = None, _: User = Depends(console)) -> list[EvidenceOut]:
    with transaction() as conn:
        return rm.evidence_rows(conn, now(), code)


@router.get("/evidence/{ref}", response_model=EvidenceOut)
def evidence_one(ref: str, _: User = Depends(console)) -> EvidenceOut:
    with transaction() as conn:
        rows = rm.evidence_rows(conn, now(), ref=ref)
    if not rows:
        raise ApiError(404, "Evidence not found", "not_found")
    return rows[0]


@router.get("/notes", response_model=list[NoteOut])
def notes_list(code: str | None = None, _: User = Depends(console)) -> list[NoteOut]:
    with transaction() as conn:
        return rm.notes_for(conn, now(), code)


@router.post("/patients/{pid}/notes", response_model=NoteOut, status_code=201)
def add_note(pid: str, body: NoteIn, user: User = Depends(require_roles("doctor"))) -> NoteOut:
    at = now()
    with transaction() as conn:
        pat = resolve_patient(conn, pid)
        by = user.display_name or user.token
        eid, _ = events_repo.append_event(
            events_repo.NewEvent(
                patient_id=pat["patient_id"],
                type="ContextNote",
                occurred_at=at,
                recorded_at=at,
                source="console",
                reporter_id=user.person_id,
                payload={"kind": "doctor_note", "text": body.text, "by": by, "at": "today"},
                idempotency_key=f"note:{new_id()}",
            ),
            conn=conn,
        )
    return NoteOut(id=str(eid), code=display_code(pat["token"]), at="today", by=by, text=body.text)


@router.get("/lens", response_model=list[LensSnapOut])
def lens_all(_: User = Depends(console)) -> list[LensSnapOut]:
    at = now()
    out: list[LensSnapOut] = []
    with transaction() as conn:
        for p in rm.ui_patients(conn, at):
            if p.code in ("PT-0900", "PT-0901"):
                out += _lens(conn, p.patient_id, p.code, at)
    return out


@router.get("/messages", response_model=list[MessageOut])
def messages_list(code: str | None = None, _: User = Depends(console)) -> list[MessageOut]:
    with transaction() as conn:
        return rm.message_rows(conn, now(), code)


@router.get("/admin/audit", response_model=Page[AuditRowOut])
def audit_list(
    patient_id: str | None = None,
    action: str | None = None,
    cursor: str | None = None,
    limit: int = 100,
    _: User = Depends(console),
) -> Page[AuditRowOut]:
    at = max(now(), datetime.now(UTC))  # login rows carry real time; the sim clock may be pinned earlier
    limit = max(1, min(limit, 500))
    offset = parse_cursor(cursor)
    where, args = ["a.at <= %s"], [at]
    with transaction() as conn:
        if patient_id:
            where.append("a.patient_id = %s")
            args.append(resolve_patient(conn, patient_id)["patient_id"])
        if action:
            where.append("a.action = %s")
            args.append(action)
        rows = conn.execute(
            "SELECT a.*, per.token AS ptoken FROM cm.audit_log a LEFT JOIN cm.patients p USING (patient_id) "
            "LEFT JOIN cm.persons per ON per.person_id = p.person_id WHERE "
            + " AND ".join(where)
            + " ORDER BY a.at DESC, a.id DESC LIMIT %s OFFSET %s",
            [*args, limit + 1, offset],
        ).fetchall()
        names = {r["actor"]: _actor_name(conn, r["actor"]) for r in rows}
    items = [_audit_row(r, names) for r in rows[:limit]]
    return Page[AuditRowOut](
        items=items, next_cursor=str(offset + limit) if len(rows) > limit else None
    )


def _actor_name(conn: Any, token: str) -> str:
    if token == "system":  # noqa: S105
        return "Assistant"
    row = conn.execute("SELECT person_id FROM cm.persons WHERE token=%s", (token,)).fetchone()
    return (display_name_of(conn, row["person_id"]) if row else None) or token


_LABEL = {
    "decision.approve": "Approved draft",
    "decision.edit": "Edited then approved",
    "decision.reject": "Declined draft",
    "assistant.draft": "Drafted",
    "patient.request": "Asked a question",
    "consent.withdrawn": "Recorded consent withdrawn",
    "consent.granted": "Recorded consent given",
    "login": "Signed in",
}


def _audit_row(r: dict[str, Any], names: dict[str, str]) -> AuditRowOut:
    tool = r["tool"]
    return AuditRowOut(
        id=r["id"],
        code=display_code(r["ptoken"]) if r["ptoken"] else None,
        at=r["at"],
        actor=names.get(r["actor"], r["actor"]),
        role=r["role"],
        action=r["action"],
        label=_LABEL.get(r["action"], r["action"]),
        src_id=r["thread_id"],
        note=None if not tool or tool.startswith("decide:") else tool,
    )
