"""Lane G: read-side assembly of the UI-shaped models from the database. All reads take as_of."""
# ruff: noqa: S608  (SQL is assembled from fixed fragments; every value is a bound parameter)

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from cm.api.deps import display_code, token_from_code
from cm.api.portal_models import (
    EvidenceOut,
    MessageOut,
    NoteOut,
    RequestOut,
    UiPatient,
)
from cm.core.clock import IST

_PATIENTS_SQL = """
SELECT p.patient_id, per.token, per.person_id, p.treatment_start, p.status, c.name AS clinic_name,
       c.clinic_id, s.payload AS sm,
       EXISTS (SELECT 1 FROM cm.support_assignments sa WHERE sa.patient_id = p.patient_id
               AND sa.from_date <= %(d)s AND (sa.to_date IS NULL OR sa.to_date >= %(d)s)) AS linked
  FROM cm.patients p JOIN cm.persons per ON per.person_id = p.person_id JOIN cm.clinics c ON c.clinic_id = p.clinic_id
  LEFT JOIN LATERAL (
    SELECT e.payload FROM cm.events e
     WHERE e.patient_id = p.patient_id AND e.type = 'ContextNote' AND e.payload->>'kind' = 'summary'
       AND e.occurred_at <= %(t)s AND e.recorded_at <= %(t)s
     ORDER BY e.occurred_at DESC LIMIT 1) s ON true
 WHERE p.status <> 'erased'
 ORDER BY per.token
"""


def sim_date(as_of: datetime) -> date:
    return as_of.astimezone(IST).date()


def clinic_slug(name: str) -> str:
    return name.split()[0].lower()


def _related(conn: Any, as_of: datetime) -> dict[UUID, list[dict[str, Any]]]:
    rows = conn.execute(
        "SELECT patient_id, status, tier, payload->>'subkind' AS subkind, "
        "COALESCE(payload->'data'->>'archived','false') = 'true' AS archived "
        "FROM cm.approvals WHERE patient_id IS NOT NULL AND created_at <= %s",
        (as_of,),
    ).fetchall()
    out: dict[UUID, list[dict[str, Any]]] = {}
    for r in rows:
        is_req = r["subkind"] == "patient_request"
        if is_req and r["archived"]:
            continue
        green = not is_req and r["tier"] == "green"
        if green and r["status"] != "pending":
            continue
        out.setdefault(r["patient_id"], []).append({**r, "is_req": is_req, "green": green})
    return out


def _level(
    base: str, tag: str, next_step: str, items: list[dict[str, Any]]
) -> tuple[str, str, str, bool, bool]:
    """Port of web/src/api/derive.ts buildRow."""
    pending = [x for x in items if x["status"] == "pending" and not x.get("green")]
    still_open = any(x["status"] == "pending" for x in items)  # includes green drafts awaiting release
    needs = bool(pending)
    has_req = any(x["is_req"] and x["status"] == "pending" for x in items)
    level, tg, nxt = base, tag, next_step
    if needs and base == "grn":
        level, tg = "blu", "ASKED"
    elif not needs and not still_open and base != "grn" and items:
        level, tg = "grn", "HANDLED"
    if not needs and items and not still_open:
        if any(x["status"] in ("approved", "edited") for x in items):
            nxt = "Approved and sent"
        elif items[-1]["status"] == "rejected":
            nxt = "Declined"
    return level, tg, nxt, needs, has_req


def ui_patients(conn: Any, as_of: datetime) -> list[UiPatient]:
    rel = _related(conn, as_of)
    today = sim_date(as_of)
    out: list[UiPatient] = []
    for r in conn.execute(_PATIENTS_SQL, {"d": today, "t": as_of}).fetchall():
        sm = r["sm"] or {}
        items = rel.get(r["patient_id"], [])
        base, tag = sm.get("base", "grn"), sm.get("tag", "ON TRACK")
        level, ltag, nxt, needs, has_req = _level(base, tag, sm.get("next_step", ""), items)
        out.append(
            UiPatient(
                patient_id=r["patient_id"],
                person_id=r["person_id"],
                token=r["token"],
                code=display_code(r["token"]),
                sex=sm.get("sex", "F"),
                age=sm.get("age", 0),
                day=(today - r["treatment_start"]).days + 1,
                base=base,
                tag=tag,
                why=sm.get("why", ""),
                missed=sm.get("missed", []),
                no_data=sm.get("no_data", 0),
                next_step=sm.get("next_step", ""),
                clinic=clinic_slug(r["clinic_name"]),
                visit_this_week=sm.get("visit_this_week", False),
                quiet=sm.get("quiet", False),
                next_visit=sm.get("next_visit", ""),
                supporter="Linked" if r["linked"] else "Not linked",
                consent=sm.get("consent", "Active"),
                changes=sm.get("changes", []),
                level=level,
                level_tag=ltag,
                needs_me=needs,
                has_request=has_req,
                open_reviews=sum(1 for x in items if x["status"] == "pending" and not x.get("green")),
            ).model_copy(update={"next_step": nxt})
        )
    return out


def evidence_rows(
    conn: Any, as_of: datetime, code: str | None = None, ref: str | None = None
) -> list[EvidenceOut]:
    where, args = (
        ["e.occurred_at <= %s", "e.recorded_at <= %s", "e.payload ? 'ref'"],
        [as_of, as_of],
    )
    if code:
        where.append("per.token = %s")
        args.append(token_from_code(code))
    if ref:
        where.append("e.payload->>'ref' = %s")
        args.append(ref)
    rows = conn.execute(
        "SELECT e.event_id, e.payload, per.token FROM cm.events e JOIN cm.patients p USING (patient_id) "
        "JOIN cm.persons per ON per.person_id = p.person_id WHERE "
        + " AND ".join(where)
        + " ORDER BY e.payload->>'ref' DESC",
        args,
    ).fetchall()
    return [
        EvidenceOut(
            id=r["payload"]["ref"],
            event_id=r["event_id"],
            code=display_code(r["token"]),
            at=r["payload"].get("at", ""),
            kind=r["payload"].get("kind", "system"),
            reporter=r["payload"].get("reporter", "System"),
            text=r["payload"].get("text", ""),
            why=r["payload"].get("why", ""),
        )
        for r in rows
    ]


def notes_for(conn: Any, as_of: datetime, code: str | None = None) -> list[NoteOut]:
    where, args = (
        ["e.type='ContextNote'", "e.payload->>'kind'='doctor_note'", "e.occurred_at <= %s"],
        [as_of],
    )
    if code:
        where.append("per.token = %s")
        args.append(token_from_code(code))
    rows = conn.execute(
        "SELECT e.event_id, e.payload, e.occurred_at, per.token FROM cm.events e JOIN cm.patients p USING (patient_id) "
        "JOIN cm.persons per ON per.person_id = p.person_id WHERE "
        + " AND ".join(where)
        + " ORDER BY e.occurred_at DESC",
        args,
    ).fetchall()
    return [
        NoteOut(
            id=str(r["event_id"]),
            code=display_code(r["token"]),
            at=r["payload"].get("at") or r["occurred_at"].isoformat(),
            by=r["payload"].get("by", ""),
            text=r["payload"].get("text", ""),
        )
        for r in rows
    ]


def request_rows(
    conn: Any, as_of: datetime, *, code: str | None = None, status: str | None = None
) -> list[RequestOut]:
    where = ["a.payload->>'subkind' = 'patient_request'", "a.created_at <= %s"]
    args: list[Any] = [as_of]
    if code:
        where.append("per.token = %s")
        args.append(token_from_code(code))
    rows = conn.execute(
        "SELECT a.*, per.token, (SELECT d.decided_at FROM cm.review_decisions d "
        "WHERE d.approval_id = a.approval_id LIMIT 1) AS decided_at "
        "FROM cm.approvals a JOIN cm.patients p USING (patient_id) "
        "JOIN cm.persons per ON per.person_id = p.person_id WHERE "
        + " AND ".join(where)
        + " ORDER BY a.created_at DESC",
        args,
    ).fetchall()
    out = []
    for r in rows:
        st = {
            "pending": "waiting",
            "approved": "approved",
            "edited": "approved",
            "rejected": "declined",
        }.get(r["status"], "waiting")
        if status and st != status:
            continue
        data = r["payload"].get("data", {})
        out.append(
            RequestOut(
                id=r["approval_id"],
                patient_code=display_code(r["token"]),
                kind=data.get("kind", "Other"),
                text=data.get("text", ""),
                when=r["created_at"],
                draft=r["payload"].get("body", ""),
                status=st,
                reply=r["payload"].get("body") if st == "approved" else None,
                due_at=r["due_at"],
                refs=data.get("refs", []),
                archived=bool(data.get("archived")),
                tier=r["tier"],
                priority=data.get("priority"),
                source=data.get("source"),
                origin=data.get("origin"),
                research=data.get("research"),
                answered_at=r["decided_at"] if st == "approved" else None,
            )
        )
    return out


def message_rows(conn: Any, as_of: datetime, code: str | None = None) -> list[MessageOut]:
    where, args = (
        ["o.created_at <= %s", "o.approval_id IS NOT NULL", "pt.patient_id IS NOT NULL"],
        [as_of],
    )
    if code:
        where.append("pp.token = %s")
        args.append(token_from_code(code))
    rows = conn.execute(
        "SELECT o.outbox_id, o.approval_id, o.body, o.channel, o.created_at, o.meta, a.status AS astatus, "
        "o.status AS ostatus, o.last_error, "
        "pp.token, a.payload, rd.doctor_id, rd.action, "
        "(SELECT enc_name FROM cm.identity_vault v WHERE v.person_id = rd.doctor_id) AS dname "
        "FROM cm.outbox o JOIN cm.approvals a USING (approval_id) "
        "JOIN cm.review_decisions rd ON rd.decision_id = o.decision_id "
        "JOIN cm.patients pt ON pt.patient_id = a.patient_id JOIN cm.persons pp ON pp.person_id = pt.person_id "
        "WHERE "
        + " AND ".join(where)
        + " AND o.recipient_id = pp.person_id ORDER BY o.created_at DESC",
        args,
    ).fetchall()
    return [
        MessageOut(
            id=r["outbox_id"],
            src_id=r["approval_id"],
            code=display_code(r["token"]),
            at=r["created_at"],
            channel=r["channel"],
            text=r["body"] or "",
            approved_by=bytes(r["dname"]).decode() if r["dname"] else "Doctor",
            version=2 if r["astatus"] == "edited" else 1,
            status="seen" if r["meta"].get("seen_at") else "sent",
            delivery={"sent": "sent", "failed": "failed"}.get(r["ostatus"], "queued"),
            delivery_error=(r["last_error"] or "")[:120] or None,
        )
        for r in rows
    ]
