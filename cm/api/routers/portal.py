"""Lane G: patient and Supporter self-service app routes (/portal/*). Models: cm/api/portal_models.py.

Every response passes the banned-term filter (cm/api/suppress.py). Patients and Supporters only ever
see doctor-approved messages (outbox rows written by decide()).
"""
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile
from psycopg.types.json import Jsonb

from cm.api import readmodels as rm
from cm.api.deps import ApiError, User, display_code, display_name_of, now, require_roles
from cm.api.portal_models import (
    Appointment,
    ConsentSwitches,
    DoseIn,
    InReplyTo,
    PortalDocument,
    PortalMe,
    PortalMedicine,
    PortalMessage,
    PortalRecord,
    PortalRequestIn,
    PortalRequestOut,
    PortalToday,
    PortalUploadOut,
    RecordDay,
    ReminderRequestIn,
    SupporterAskIn,
    SupporterRef,
    SupporterView,
)
from cm.api.suppress import clean_texts, is_clean
from cm.channels import question_routing
from cm.core.db import transaction
from cm.core.ids import new_id
from cm.core.logging import get_logger
from cm.store import approvals_repo, events_repo, outbox_repo, uploads_repo
from cm.store import consent as consent_repo
from cm.uploads import intake as upload_intake
from cm.uploads.validate import max_bytes

log = get_logger()
router = APIRouter(prefix="/portal", tags=["portal"])
patient_only = require_roles("patient")
supporter_only = require_roles("supporter")
SOURCES = ("telegram", "gmail", "calendar")


# ---- helpers ------------------------------------------------------------------------------
def _my_patient(conn: Any, user: User) -> dict[str, Any]:
    row = conn.execute(
        "SELECT p.*, c.name AS clinic_name FROM cm.patients p JOIN cm.clinics c USING (clinic_id) "
        "WHERE p.person_id=%s",
        (user.person_id,),
    ).fetchone()
    if not row:
        raise ApiError(404, "No patient record for this account", "not_found")
    return row


def _assigned_patient(conn: Any, user: User, at: datetime) -> dict[str, Any]:
    d = rm.sim_date(at)
    row = conn.execute(
        "SELECT p.*, c.name AS clinic_name FROM cm.support_assignments sa JOIN cm.patients p USING (patient_id) "
        "JOIN cm.clinics c USING (clinic_id) WHERE sa.supporter_id=%s AND sa.from_date <= %s "
        "AND (sa.to_date IS NULL OR sa.to_date >= %s) LIMIT 1",
        (user.person_id, d, d),
    ).fetchone()
    if not row:
        raise ApiError(403, "No assigned patient", "forbidden_scope")
    return row


def _relation(summary: dict[str, Any]) -> str | None:
    """Supporter relation as recorded by the clinic; never invented, withheld if it holds a banned word."""
    rel = summary.get("supporter_relation")
    return rel if isinstance(rel, str) and rel.strip() and is_clean(rel) else None


def _appt_visible(payload: dict[str, Any]) -> bool:
    """An appointment row is shown only if none of its texts holds a banned word (withheld, never rewritten)."""
    return all(is_clean(str(payload.get(f) or "")) for f in ("title", "when", "place", "note"))


def _summary(conn: Any, patient_id: UUID, at: datetime) -> dict[str, Any]:
    for r in events_repo.query(patient_id, at, types=["ContextNote"], conn=conn):
        if r["payload"].get("kind") == "summary":
            return r["payload"]
    return {}


def _doses(conn: Any, patient_id: UUID, at: datetime) -> dict[date, dict[str, Any]]:
    """Latest dose event per sim date (later events supersede earlier ones)."""
    by_day: dict[date, dict[str, Any]] = {}
    rows = events_repo.query(patient_id, at, types=["DoseCheckin"], conn=conn)
    replaced = {r["supersedes"] for r in rows if r["supersedes"]}  # same-instant edits tie on time
    for r in sorted(
        (r for r in rows if r["event_id"] not in replaced), key=lambda x: x["occurred_at"]
    ):
        by_day[rm.sim_date(r["occurred_at"])] = r
    return by_day


def _status(ev: dict[str, Any] | None) -> str:
    return {"taken": "o", "missed": "m"}.get((ev or {}).get("payload", {}).get("status", ""), "f")


def _history(doses: dict[date, dict[str, Any]], today: date, n: int = 60) -> str:
    return "".join(_status(doses.get(today - timedelta(days=n - 1 - i))) for i in range(n))


def _streak(hist: str) -> int:
    body = hist[:-1] if hist.endswith("f") else hist
    count = 0
    for c in reversed(body):
        if c != "o":
            break
        count += 1
    return count + (1 if hist.endswith("o") else 0)


def _marked_by(ev: dict[str, Any] | None) -> str | None:
    if not ev or _status(ev) == "f":
        return None
    return "supporter" if ev["reporter_mode"] == "witnessed" else "self"


def _record_dose(
    conn: Any,
    patient: dict[str, Any],
    source: str,
    mode: str,
    reporter: UUID,
    consent_source: str,
    status: str,
    reason: str | None,
    at: datetime,
) -> None:
    today = rm.sim_date(at)
    existing = [e for d, e in _doses(conn, patient["patient_id"], at).items() if d == today]
    if existing and existing[0]["payload"].get("status") == status:
        return
    _append_dose(
        conn, patient, source, mode, reporter, consent_source, status, reason, at, existing
    )


def _append_dose(
    conn: Any,
    patient: dict[str, Any],
    source: str,
    mode: str,
    reporter: UUID,
    consent_source: str,
    status: str,
    reason: str | None,
    at: datetime,
    existing: list[dict[str, Any]],
) -> None:
    today = rm.sim_date(at)
    consent_id = consent_repo.latest_consent_id(patient["person_id"], consent_source, at, conn=conn)
    n = conn.execute(
        "SELECT count(*) AS n FROM cm.events WHERE patient_id=%s AND type='DoseCheckin' "
        "AND idempotency_key LIKE %s",
        (patient["patient_id"], f"{source}:dose:{patient['patient_id']}:{today}:%"),
    ).fetchone()["n"]
    events_repo.append_event(
        events_repo.NewEvent(
            patient_id=patient["patient_id"],
            type="DoseCheckin",
            occurred_at=at,
            recorded_at=at,
            source=source,
            reporter_id=reporter,
            reporter_mode=mode,
            channel="portal",
            consent_id=consent_id,
            payload={"status": status, "reason": reason, "kind": "dose", "marked_by": mode},
            supersedes=existing[0]["event_id"] if existing else None,
            idempotency_key=f"{source}:dose:{patient['patient_id']}:{today}:{n}",
        ),
        conn=conn,
    )


def _messages(
    conn: Any, person_id: UUID, at: datetime, supporter: bool = False
) -> list[PortalMessage]:
    out = []
    for r in outbox_repo.inbox_for(person_id, at, conn=conn):
        data = r["meta"] or {}
        if supporter and not data.get("for_supporter"):
            continue
        out.append(
            {
                "id": r["outbox_id"],
                "title": data.get("patient_title") or r["title"] or "Message",
                "text": r["body"],
                "created_at": r["created_at"],
                "read": bool(data.get("seen_at")),
                "for_supporter": bool(data.get("for_supporter")),
                "in_reply_to": _in_reply_to(data.get("reply_to")),
            }
        )
    return [PortalMessage(**m) for m in clean_texts(out, ("title", "text"))]


def _in_reply_to(raw: Any) -> InReplyTo | None:
    """Patient-safe link to the question a reply answers: its id and a clean short excerpt, nothing else."""
    if not isinstance(raw, dict) or not raw.get("approval_id"):
        return None
    excerpt = str(raw.get("question_excerpt") or "")
    return InReplyTo(
        approval_id=UUID(str(raw["approval_id"])),
        question_excerpt=excerpt if is_clean(excerpt) else "",
    )


def _new_request(
    conn: Any,
    patient: dict[str, Any],
    text: str,
    kind: str,
    draft: str,
    extra: dict[str, Any],
    at: datetime,
) -> UUID:
    rid = new_id()
    aid = approvals_repo.upsert(
        {
            "approval_id": rid,
            "patient_id": patient["patient_id"],
            "thread_id": f"req-{rid}",
            "interrupt_id": "req",
            "tier": "green",
            "kind": "needs_human",
            "created_at": at,
            "due_at": at + timedelta(hours=4),
            "expires_at": at + timedelta(hours=48),
            "payload": {
                "audience": "patient",
                "title": f"Patient request: {kind}",
                "channel": "web_inbox",
                "recipients": [
                    {"person_id": str(patient["person_id"]), "token": "", "channel": "web_inbox"}
                ],
                "body": draft,
                "subkind": "patient_request",
                "data": {"kind": kind, "text": text, "refs": [], **extra},
            },
        },
        conn=conn,
    )
    conn.execute(
        "INSERT INTO cm.audit_log (at, actor, role, action, patient_id, thread_id) VALUES (%s,%s,'patient','patient.request',%s,%s)",
        (at, _token_of(conn, patient), patient["patient_id"], f"req-{rid}"),
    )
    return aid


# ---- patient routes -------------------------------------------------------------------------
@router.get("/me", response_model=PortalMe)
def portal_me(user: User = Depends(patient_only)) -> PortalMe:
    at = now()
    with transaction() as conn:
        p = _my_patient(conn, user)
        sm = _summary(conn, p["patient_id"], at)
        sup = conn.execute(
            "SELECT sa.supporter_id FROM cm.support_assignments sa WHERE sa.patient_id=%s AND sa.to_date IS NULL "
            "LIMIT 1",
            (p["patient_id"],),
        ).fetchone()
        reqs = [
            r
            for r in rm.request_rows(conn, at, code=display_code(user.token))
            if r.kind == "Reminder time"
        ]
        state = consent_repo.consent_state(user.person_id, at, conn=conn)
        name = display_name_of(conn, user.person_id) or user.token
        sup_name = display_name_of(conn, sup["supporter_id"]) if sup else None
    approved = next((r for r in reqs if r.status == "approved"), None)
    pending = next((r for r in reqs if r.status == "waiting"), None)
    return PortalMe(
        patient_code=display_code(user.token),
        name=name,
        clinic=p["clinic_name"],
        day=(rm.sim_date(at) - p["treatment_start"]).days + 1,
        supporter=SupporterRef(name=sup_name, relation=_relation(sm)) if sup_name else None,
        reminder=_time_of(approved),
        pending_reminder=_time_of(pending),
        consents={s: any(v == "granted" for v in state.get(s, {}).values()) for s in SOURCES},
    )


def _time_of(req: Any) -> str | None:
    if not req:
        return None
    m = re.search(r"\d{1,2}:\d{2} (?:am|pm)", req.draft or "")
    return m.group(0) if m else None


@router.get("/today", response_model=PortalToday)
def portal_today(user: User = Depends(patient_only)) -> PortalToday:
    at = now()
    with transaction() as conn:
        p = _my_patient(conn, user)
        doses = _doses(conn, p["patient_id"], at)
        sm = _summary(conn, p["patient_id"], at)
    today = rm.sim_date(at)
    hist = _history(doses, today)
    ev = doses.get(today)
    nv = sm.get("next_visit")
    from cm.api.own_data import safe_when  # same slot rule as the own-data answer cards

    next_visit = nv if isinstance(nv, str) and safe_when(nv) else None
    return PortalToday(
        today={"o": "taken", "m": "missed"}.get(hist[-1], "none"),  # type: ignore[arg-type]
        reason=(ev or {}).get("payload", {}).get("reason") if ev else None,
        marked_by=_marked_by(ev),  # type: ignore[arg-type]
        streak=_streak(hist),
        next_visit=next_visit,
        history=hist,
    )


@router.post("/dose", response_model=PortalToday)
def portal_dose(body: DoseIn, user: User = Depends(patient_only)) -> PortalToday:
    at = now()
    with transaction() as conn:
        p = _my_patient(conn, user)
        _record_dose(conn, p, "web", "self", user.person_id, "web", body.status, body.reason, at)
    return portal_today(user)


@router.delete("/dose", response_model=PortalToday)
def portal_undo_dose(user: User = Depends(patient_only)) -> PortalToday:
    """Undo today's dose with a compensating event (status 'undone', supersedes the mark).

    The log is append-only: no row is deleted. Idempotent: with nothing to undo it changes nothing.
    """
    at = now()
    with transaction() as conn:
        p = _my_patient(conn, user)
        today = rm.sim_date(at)
        cur = _doses(conn, p["patient_id"], at).get(today)
        if cur and cur["payload"].get("status") in ("taken", "missed"):
            _append_dose(conn, p, "web", "self", user.person_id, "web", "undone", None, at, [cur])
    return portal_today(user)


# internal extra.upload_state -> what the patient may see
_UPLOAD_STATUS = {
    "received": "received",
    "extracting": "received",
    "pending_review": "with your care team",
    "accepted": "added to your record",
    "indexed": "added to your record",  # approved and searchable (the final state after approval)
    "rejected": "could not be used",
    "failed": "could not be used",
}
_UPLOAD_ERRORS = {
    "no_consent": (403, "Please allow us to keep your documents in your settings first."),
    "too_large": (413, "This file is too large. Please send one that is smaller."),
    "bad_type": (415, "We can only accept photos (JPG or PNG), PDF files and plain text files."),
    "rate_limited": (429, "You have sent several documents recently. Please try again later."),
    "unknown_patient": (404, "No patient record for this account"),
}


def _upload_rows(conn: Any, token: str) -> list[dict[str, Any]]:
    out = []
    for r in uploads_repo.list_for_patient(token, conn=conn):
        ex = r["extra"]
        name = ex.get("filename") or "document"
        out.append(
            {
                "id": str(r["document_id"]),
                "title": name if is_clean(name) else "Uploaded document",  # shown, never dropped
                "kind": "other",
                "date": rm.sim_date(r["recorded_at"]),
                "summary": "",
                "status": _UPLOAD_STATUS.get(ex.get("upload_state", ""), "received"),
            }
        )
    return out


@router.get("/documents", response_model=list[PortalDocument])
def portal_documents(user: User = Depends(patient_only)) -> list[PortalDocument]:
    at = now()
    with transaction() as conn:
        p = _my_patient(conn, user)
        notes = [
            e
            for e in events_repo.query(p["patient_id"], at, types=["ContextNote"], conn=conn)
            if e["payload"].get("kind") == "document"
        ]
        uploads = _upload_rows(conn, user.token)
    out = [
        {
            "id": e["payload"]["id"],
            "title": e["payload"]["title"],
            "kind": e["payload"].get("doc_kind", "other"),
            "date": rm.sim_date(e["occurred_at"]),
            "summary": e["payload"].get("summary", ""),
        }
        for e in sorted(notes, key=lambda x: x["occurred_at"], reverse=True)
    ]
    docs = [PortalDocument(**d) for d in clean_texts(out, ("title", "summary"))]
    return sorted([*docs, *(PortalDocument(**u) for u in uploads)], key=lambda d: d.date, reverse=True)


def _enqueue_extract(document_id: str) -> None:
    """Idempotent (task docx-<id>). The row is committed already; a queue error must not fail the upload."""
    try:
        from cm.uploads.review import enqueue_extract

        enqueue_extract(document_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("extract enqueue failed", error=type(exc).__name__)


@router.post("/documents", response_model=PortalUploadOut, status_code=201)
async def portal_upload_document(
    request: Request, file: UploadFile = File(...), user: User = Depends(patient_only)
) -> PortalUploadOut:
    """Upload one file. The patient comes from the session only; size is enforced while streaming."""
    cap = max_bytes()
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > cap + 64 * 1024:  # multipart framing slack
        raise ApiError(413, _UPLOAD_ERRORS["too_large"][1], "too_large")
    buf = bytearray()
    while chunk := await file.read(64 * 1024):
        buf += chunk
        if len(buf) > cap:
            raise ApiError(413, _UPLOAD_ERRORS["too_large"][1], "too_large")
    res = upload_intake.accept_upload(
        patient_token=user.token,
        source="portal",
        filename=file.filename or "document",
        mime=file.content_type or "",
        data=bytes(buf),
        uploader_person_id=user.person_id,
    )
    if res.reason and res.reason != "duplicate":
        status, title = _UPLOAD_ERRORS.get(
            res.reason, (503, "We could not save your document. Please try again later.")
        )
        raise ApiError(status, title, res.reason)
    if res.document_id and not res.duplicate:
        _enqueue_extract(res.document_id)
    return PortalUploadOut(
        document_id=res.document_id,
        status=_UPLOAD_STATUS.get(res.status, "received"),
        duplicate=res.duplicate,
    )


@router.get("/medicines", response_model=list[PortalMedicine])
def portal_medicines(user: User = Depends(patient_only)) -> list[PortalMedicine]:
    at = now()
    with transaction() as conn:
        p = _my_patient(conn, user)
        notes = [
            e
            for e in events_repo.query(p["patient_id"], at, types=["ContextNote"], conn=conn)
            if e["payload"].get("kind") == "medicine"
        ]
    out = [
        {
            "id": e["payload"]["id"],
            "label": e["payload"]["label"],
            "when": e["payload"]["when"],
            "note": e["payload"].get("note"),
            "o": e["payload"].get("order", 0),
        }
        for e in notes
    ]
    out.sort(key=lambda x: x["o"])
    return [
        PortalMedicine(**{k: v for k, v in m.items() if k != "o"})
        for m in clean_texts(out, ("label", "when", "note"))
    ]


@router.get("/record", response_model=PortalRecord)
def portal_record(user: User = Depends(patient_only)) -> PortalRecord:
    at = now()
    with transaction() as conn:
        p = _my_patient(conn, user)
        doses = _doses(conn, p["patient_id"], at)
        notes = [
            e
            for e in events_repo.query(p["patient_id"], at, types=["ContextNote"], conn=conn)
            if e["payload"].get("kind") == "appointment"
        ]
    today = rm.sim_date(at)
    days = []
    for i in range(60):
        d = today - timedelta(days=59 - i)
        ev = doses.get(d)
        st = {"o": "taken", "m": "missed"}.get(_status(ev), "none")
        days.append(
            RecordDay(
                date=d,
                status=st,
                reason=(ev or {}).get("payload", {}).get("reason") if ev else None,
            )
        )  # type: ignore[arg-type]
    appts: dict[str, list[Appointment]] = {"upcoming": [], "past": []}
    for e in sorted(notes, key=lambda x: x["payload"].get("order", 0)):
        pl = e["payload"]
        if not _appt_visible(pl) or pl.get("bucket", "past") not in appts:
            continue
        appts[pl.get("bucket", "past")].append(
            Appointment(
                id=str(e["event_id"]),
                kind=pl["appt_kind"],
                title=pl["title"],
                when=pl["when"],
                place=pl["place"],
                note=pl.get("note"),
            )
        )
    return PortalRecord(
        days=days,
        taken=sum(d.status == "taken" for d in days),
        missed=sum(d.status == "missed" for d in days),
        **appts,
    )


@router.get("/inbox", response_model=list[PortalMessage])
def portal_inbox(
    user: User = Depends(require_roles("patient", "supporter")),
) -> list[PortalMessage]:
    with transaction() as conn:
        return _messages(conn, user.person_id, now(), supporter=user.role == "supporter")


@router.post("/messages/{outbox_id}/read", status_code=204)
def mark_read(outbox_id: UUID, user: User = Depends(require_roles("patient", "supporter"))) -> None:
    with transaction() as conn:
        row = conn.execute(
            "UPDATE cm.outbox SET meta = meta || %s WHERE outbox_id=%s AND recipient_id=%s RETURNING outbox_id",
            (Jsonb({"seen_at": now().isoformat()}), outbox_id, user.person_id),
        ).fetchone()
    if not row:
        raise ApiError(404, "Message not found", "not_found")


# waiting until the doctor replies; a declined question is "closed" (no reply is coming, no false hope)
_QSTATUS = {"waiting": "waiting", "approved": "answered", "declined": "closed"}


def _my_requests(conn: Any, user: User, at: datetime) -> list[PortalRequestOut]:
    rows = rm.request_rows(conn, at, code=display_code(user.token))
    out = [
        {
            "id": r.id,
            "text": r.text,
            "kind": r.kind,
            "when": r.when,
            "status": r.status,
            "reply": r.reply,
            "question_status": _QSTATUS[r.status],
            "answered_at": r.answered_at,
        }
        for r in rows
    ]
    return [PortalRequestOut(**o) for o in clean_texts(out, ("text", "kind", "reply"))]


RECEIVED = "Your message was sent to your care team."


def _created(conn: Any, user: User, rid: UUID, at: datetime) -> PortalRequestOut:
    """The row just written, as the patient may see it. Words the patient typed that we may not show
    back (non-negotiable 5) are replaced by a plain receipt; the doctor still reads the original."""
    hit = next((r for r in _my_requests(conn, user, at) if r.id == rid), None)
    if hit:
        return hit
    raw = next(r for r in rm.request_rows(conn, at, code=display_code(user.token)) if r.id == rid)
    return PortalRequestOut(
        id=raw.id,
        text=RECEIVED,
        kind=raw.kind if is_clean(raw.kind) else "Other",
        when=raw.when,
        status=raw.status,
        reply=None,
        question_status=_QSTATUS[raw.status],
    )


@router.get("/requests", response_model=list[PortalRequestOut])
def portal_requests(user: User = Depends(patient_only)) -> list[PortalRequestOut]:
    with transaction() as conn:
        return _my_requests(conn, user, now())


@router.post("/requests", response_model=PortalRequestOut, status_code=201)
def portal_new_request(
    body: PortalRequestIn, user: User = Depends(patient_only)
) -> PortalRequestOut:
    at = now()
    with transaction() as conn:
        p = _my_patient(conn, user)
        rid = _new_request(
            conn,
            p,
            body.text,
            body.kind,
            "Thank you for your message. Your care team will reply soon.",
            {
                "source": "portal",
                "category": "question",
                "origin": question_routing.build_origin("portal", body.text),
                "research": question_routing.blank_research(),
            },
            at,
        )
        created = _created(conn, user, rid, at)
    question_routing.enqueue_research(rid)  # after commit; idempotent per approval
    return created


@router.post("/reminder-request", response_model=PortalRequestOut, status_code=201)
def portal_reminder_request(
    body: ReminderRequestIn, user: User = Depends(patient_only)
) -> PortalRequestOut:
    at = now()
    with transaction() as conn:
        p = _my_patient(conn, user)
        rid = _new_request(
            conn,
            p,
            f"Please change my reminder to {body.time}.",
            "Reminder time",
            f"Your reminder is now {body.time}. Tell us if you want to change it again.",
            {"reminder_time": body.time},
            at,
        )
        created = _created(conn, user, rid, at)
    return created


def _switches(conn: Any, person_id: UUID, at: datetime) -> ConsentSwitches:
    state = consent_repo.consent_state(person_id, at, conn=conn)
    return ConsentSwitches(
        **{s: any(v == "granted" for v in state.get(s, {}).values()) for s in SOURCES}
    )


@router.get("/consents", response_model=ConsentSwitches)
def get_consents(user: User = Depends(patient_only)) -> ConsentSwitches:
    with transaction() as conn:
        return _switches(conn, user.person_id, now())


@router.put("/consents", response_model=ConsentSwitches)
def put_consents(body: ConsentSwitches, user: User = Depends(patient_only)) -> ConsentSwitches:
    at = now()
    with transaction() as conn:
        cur = _switches(conn, user.person_id, at)
        for s in SOURCES:
            want = getattr(body, s)
            if want != getattr(cur, s):
                consent_repo.record_consent(
                    user.person_id,
                    s,
                    "care_coordination",
                    "granted" if want else "withdrawn",
                    at,
                    "web",
                    conn=conn,
                )
                conn.execute(
                    "INSERT INTO cm.audit_log (at, actor, role, action, patient_id, tool) "
                    "SELECT %s, %s, 'patient', %s, patient_id, %s FROM cm.patients WHERE person_id=%s",
                    (
                        at,
                        user.token,
                        "consent.granted" if want else "consent.withdrawn",
                        s,
                        user.person_id,
                    ),
                )
        return _switches(conn, user.person_id, at)


# ---- Supporter routes ------------------------------------------------------------------------
def _supporter_allowed(conn: Any, p: dict[str, Any], at: datetime) -> bool:
    st = consent_repo.consent_state(p["person_id"], at, conn=conn).get("supporter", {})
    return st.get("supporter_sharing") == "granted"


@router.get("/supporter/checkin", response_model=SupporterView)
def supporter_view(user: User = Depends(supporter_only)) -> SupporterView:
    at = now()
    with transaction() as conn:
        p = _assigned_patient(conn, user, at)
        sm = _summary(conn, p["patient_id"], at)
        allowed = _supporter_allowed(conn, p, at)
        pname = display_name_of(conn, p["person_id"]) or "Patient"
        ptoken = _token_of(conn, p)
        sname = display_name_of(conn, user.person_id) or user.token
        doses = _doses(conn, p["patient_id"], at) if allowed else {}
        msgs = _messages(conn, user.person_id, at, supporter=True) if allowed else []
    today = rm.sim_date(at)
    hist = _history(doses, today, 7)
    ev = doses.get(today)
    return SupporterView(
        patient_code=display_code(ptoken),
        patient_name=pname,
        supporter_name=sname,
        relation=_relation(sm),
        allowed=allowed,
        today={"o": "taken", "m": "missed"}.get(hist[-1], "none"),  # type: ignore[arg-type]
        marked_by=_marked_by(ev),
        week=hist,
        messages=msgs,
    )


def _token_of(conn: Any, p: dict[str, Any]) -> str:
    return conn.execute(
        "SELECT token FROM cm.persons WHERE person_id=%s", (p["person_id"],)
    ).fetchone()["token"]


@router.post("/supporter/mark-taken", response_model=SupporterView)
def supporter_mark(user: User = Depends(supporter_only)) -> SupporterView:
    at = now()
    with transaction() as conn:
        p = _assigned_patient(conn, user, at)
        if not _supporter_allowed(conn, p, at):
            raise ApiError(403, "The patient has not allowed this", "forbidden_scope")
        _record_dose(
            conn, p, "supporter", "witnessed", user.person_id, "supporter", "taken", None, at
        )
    return supporter_view(user)


@router.post("/supporter/ask", response_model=PortalRequestOut, status_code=201)
def supporter_ask(body: SupporterAskIn, user: User = Depends(supporter_only)) -> PortalRequestOut:
    at = now()
    with transaction() as conn:
        p = _assigned_patient(conn, user, at)
        if not _supporter_allowed(conn, p, at):
            raise ApiError(403, "The patient has not allowed this", "forbidden_scope")
        who = display_name_of(conn, user.person_id) or "Supporter"
        rid = _new_request(
            conn,
            p,
            f"(From Supporter {who}) {body.text}",
            "Supporter question",
            "Thank you for your message. Your care team will reply soon.",
            {},
            at,
        )
        row = rm.request_rows(conn, at)
    r = next(x for x in row if x.id == rid)
    if not is_clean(r.text):
        raise ApiError(422, "Message not accepted", "banned_term")
    return PortalRequestOut(
        id=r.id, text=r.text, kind=r.kind, when=r.when, status=r.status, reply=r.reply
    )
