"""Lane B: seed consents, events (evidence), patient summaries, lens snapshots, notes, appointments, doses."""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from cm.core import clock
from cm.core.ids import det_id
from cm.jobs import seed_patient_app as app
from cm.store import consent as consent_repo
from cm.store import events_repo as ev
from cm.store.events_repo import NewEvent

if TYPE_CHECKING:
    from cm.jobs.seed import Ctx

# UI reporter label -> (event source, reporter_mode, consent source, lag)
REPORTER = {
    "Patient app": ("web", "self", "web", timedelta(minutes=5)),
    "Chemist feed": ("chemist", "record", "chemist", timedelta(days=1)),
    "Supporter": ("supporter", "witnessed", "supporter", timedelta(minutes=5)),
    "Clinic": ("console", "record", None, timedelta(minutes=5)),
    "Lab feed": ("lab", "record", "lab", timedelta(days=1)),
    "System": ("system", "record", None, timedelta(minutes=1)),
    "Memory engine": ("system", "record", None, timedelta(minutes=1)),
    "Risk rules": ("system", "record", None, timedelta(minutes=1)),
}
TYPE_OF = {"refill": "Dispense", "lab": "LabResult", "supporter": "SupporterVisit"}
CONSENT_SOURCES = ("web", "telegram", "chemist", "lab", "supporter")
DAY_RE = re.compile(r"Day (\d+)(?: · (\d\d):(\d\d))?")


def at_local(start: Any, day: int, hh: int, mm: int) -> datetime:
    return datetime.combine(start + timedelta(days=day - 1), time(hh, mm), tzinfo=clock.IST)


def parse_day(label: str, start: Any, default_hour: int = 9) -> datetime:
    m = DAY_RE.match(label)
    day, hh, mm = int(m.group(1)), int(m.group(2) or default_hour), int(m.group(3) or 0)
    return at_local(start, day, hh, mm)


def seed_consents(ctx: Ctx) -> dict[str, dict[str, Any]]:
    """Grant consents at treatment start; withdraw Supporter sharing for the consent-withdrawn patient."""
    out: dict[str, dict[str, Any]] = {}
    for code, p in ctx.patients.items():
        start_at = at_local(p["start"], 1, 8, 0)
        have = {
            r["source"]
            for r in ctx.conn.execute(
                "SELECT DISTINCT source FROM cm.consents WHERE person_id=%s", (p["person_id"],)
            ).fetchall()
        }
        if not have:
            for src in CONSENT_SOURCES:
                purposes = ["care_coordination"] + (
                    ["supporter_sharing"] if src == "supporter" else []
                )
                for purpose in purposes:
                    consent_repo.record_consent(
                        p["person_id"], src, purpose, "granted", start_at, "console", conn=ctx.conn
                    )
            if p["row"]["consent"] == "Withdrawn":
                w = at_local(p["start"], p["row"]["day"], 11, 0)
                for purpose in ("care_coordination", "supporter_sharing"):
                    consent_repo.record_consent(
                        p["person_id"],
                        "supporter",
                        purpose,
                        "withdrawn",
                        w,
                        "console",
                        conn=ctx.conn,
                    )
        out[code] = {
            s: consent_repo.latest_consent_id(p["person_id"], s, ctx.sim_now, conn=ctx.conn)
            for s in CONSENT_SOURCES
        }
    return out


def _event(ctx: Ctx, code: str, e: dict[str, Any], consents: dict[str, Any]) -> NewEvent:
    p = ctx.patients[code]
    source, mode, csrc, lag = REPORTER.get(e["reporter"], REPORTER["System"])
    occurred = parse_day(e["at"], p["start"], 9)
    recorded = min(occurred + lag, ctx.sim_now - timedelta(minutes=1))
    return NewEvent(
        event_id=det_id("event", e["id"]),
        patient_id=p["patient_id"],
        type=TYPE_OF.get(e["kind"], "ContextNote"),
        occurred_at=occurred,
        recorded_at=recorded,
        source=source,
        reporter_mode=mode,
        consent_id=consents[code].get(csrc) if csrc else None,
        payload={
            "ref": e["id"],
            "kind": e["kind"],
            "text": e["text"],
            "why": e["why"],
            "reporter": e["reporter"],
            "at": e["at"],
        },
        idempotency_key=f"seed:{e['id']}",
    )


def seed_evidence(ctx: Ctx, consents: dict[str, dict[str, Any]]) -> None:
    events = [
        _event(ctx, e["code"], e, consents)
        for e in ctx.state["evidence"]
        if e["code"] in ctx.patients
    ]
    ctx.bump("events", len(events))
    ev.bulk_append(events, conn=ctx.conn)


def seed_summaries(ctx: Ctx) -> None:
    """The per-patient status row the memory engine will own later (kind 'summary')."""
    out = []
    for code, p in ctx.patients.items():
        r = p["row"]
        payload = {
            "kind": "summary",
            "sex": r["sex"],
            "age": r["age"],
            "base": r["base"],
            "tag": r["tag"],
            "why": r["why"],
            "missed": r["missed"],
            "no_data": r["noData"],
            "next_step": r["nextStep"],
            "visit_this_week": r["visitThisWeek"],
            "quiet": r["quiet"],
            "next_visit": r["nextVisit"],
            "consent": r["consent"],
            "changes": r["changes"],
        }
        if code == "PT-0142":
            payload["supporter_relation"] = "sister"
        occurred = at_local(p["start"], r["day"], 6, 0)
        out.append(
            NewEvent(
                patient_id=p["patient_id"],
                type="ContextNote",
                occurred_at=occurred,
                recorded_at=occurred,
                source="system",
                payload=payload,
                idempotency_key=f"seed:summary:{code}",
            )
        )
    ev.bulk_append(out, conn=ctx.conn)


def seed_lens_notes_appts(ctx: Ctx, consents: dict[str, dict[str, Any]]) -> None:
    out: list[NewEvent] = []
    for lens in ctx.state["lens"]:
        p = ctx.patients.get(lens["code"])
        if not p:
            continue
        t = at_local(p["start"], lens["day"], 9, 0)
        out.append(
            NewEvent(
                patient_id=p["patient_id"],
                type="ContextNote",
                occurred_at=t,
                recorded_at=t,
                source="system",
                payload={
                    "kind": "lens",
                    "lens": {k: lens[k] for k in ("day", "known", "beliefs", "risk", "conflicts")},
                },
                idempotency_key=f"seed:lens:{lens['code']}:{lens['day']}",
            )
        )
    for n in ctx.state["notes"]:
        p = ctx.patients.get(n["code"])
        if p:
            t = parse_day(n["at"], p["start"])
            out.append(
                NewEvent(
                    patient_id=p["patient_id"],
                    type="ContextNote",
                    occurred_at=t,
                    recorded_at=t,
                    source="console",
                    reporter_id=ctx.doctor_id,
                    payload={
                        "kind": "doctor_note",
                        "text": n["text"],
                        "by": n["by"],
                        "at": n["at"],
                    },
                    idempotency_key=f"seed:{n['id']}",
                )
            )
    p = ctx.patients.get("PT-0142")
    if p:
        for i, a in enumerate(app.APPOINTMENTS):
            t = ctx.sim_now - timedelta(days=a.get("days_ago", 0) or 0, minutes=10 + i)
            out.append(
                NewEvent(
                    patient_id=p["patient_id"],
                    type="ContextNote",
                    occurred_at=t,
                    recorded_at=t,
                    source="console",
                    payload={
                        "kind": "appointment",
                        "order": i,
                        **{k: v for k, v in a.items() if k != "days_ago"},
                    },
                    idempotency_key=f"seed:appt:{a['id']}",
                )
            )
        for i, (did, ago, dk, title, summary) in enumerate(app.DOCUMENTS):
            t = ctx.sim_now - timedelta(days=ago, minutes=30 + i)
            out.append(
                _note(
                    p,
                    t,
                    f"seed:doc:{did}",
                    {
                        "kind": "document",
                        "id": did,
                        "doc_kind": dk,
                        "title": title,
                        "summary": summary,
                    },
                )
            )
        for i, (mid, label, when, note) in enumerate(app.MEDICINES):
            t = ctx.sim_now - timedelta(days=30, minutes=40 + i)
            out.append(
                _note(
                    p,
                    t,
                    f"seed:med:{mid}",
                    {
                        "kind": "medicine",
                        "id": mid,
                        "label": label,
                        "when": when,
                        "note": note,
                        "order": i,
                    },
                )
            )
    ev.bulk_append(out, conn=ctx.conn)
    ctx.bump("events", len(out))


def _note(p: dict[str, Any], t: datetime, key: str, payload: dict[str, Any]) -> NewEvent:
    return NewEvent(
        patient_id=p["patient_id"],
        type="ContextNote",
        occurred_at=t,
        recorded_at=t,
        source="console",
        payload=payload,
        idempotency_key=key,
    )


def seed_dose_history(ctx: Ctx, consents: dict[str, dict[str, Any]]) -> None:
    p = ctx.patients.get("PT-0142")
    if not p:
        return
    out = []
    for i, c in enumerate(app.HISTORY60[:59]):
        day = ctx.today - timedelta(days=59 - i)
        t = datetime.combine(day, time(8, 0), tzinfo=clock.IST)
        reason = app.MISS_REASON.get(i) if c == "m" else None
        out.append(
            NewEvent(
                patient_id=p["patient_id"],
                type="DoseCheckin",
                occurred_at=t,
                recorded_at=t + timedelta(minutes=2),
                source="web",
                reporter_id=p["person_id"],
                reporter_mode="self",
                channel="portal",
                consent_id=consents["PT-0142"]["web"],
                payload={"status": "taken" if c == "o" else "missed", "reason": reason},
                idempotency_key=f"seed:dose:PT-0142:{day.isoformat()}",
            )
        )
    ev.bulk_append(out, conn=ctx.conn)
    ctx.bump("dose_events", len(out))


def seed_consents_and_events(ctx: Ctx) -> None:
    consents = seed_consents(ctx)
    seed_evidence(ctx, consents)
    seed_summaries(ctx)
    seed_lens_notes_appts(ctx, consents)
    seed_dose_history(ctx, consents)
