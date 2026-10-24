"""Lane B: seed approvals, patient requests, historical decisions (through decide()) and audit rows."""

from __future__ import annotations

import json
import re
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from cm.contracts.review import ReviewDecisionIn
from cm.core import clock
from cm.core.ids import det_id
from cm.jobs import seed_patient_app as app
from cm.jobs.seed_events import REPORTER, at_local, parse_day
from cm.review.decide import decide
from cm.store import approvals_repo

if TYPE_CHECKING:
    from cm.jobs.seed import Ctx

ALIAS = {"old-1": "rq-0"}  # message m-5 is the reply of the archived request rq-0
LETTER = {"E": "event", "B": "belief", "C": "conflict", "R": "risk"}
TIME_RE = re.compile(r"(\d\d):(\d\d)")


def parse_when(label: str, ctx: Ctx, start: Any) -> datetime:
    """'today 09:12', 'yesterday 18:05', '2 days ago 10:30', 'last week', 'Day 47 · 08:30' -> aware datetime."""
    if label.startswith("Day "):
        return parse_day(label, start)
    m = TIME_RE.search(label)
    hh, mm = (int(m.group(1)), int(m.group(2))) if m else (10, 0)
    if label.startswith("today"):
        back = 0
    elif label.startswith("yesterday"):
        back = 1
    elif label.startswith("last week"):
        back = 7
    else:
        back = int(re.match(r"(\d+) days ago", label).group(1))  # type: ignore[union-attr]
    return datetime.combine(ctx.today - timedelta(days=back), time(hh, mm), tzinfo=clock.IST)


def evidence_items(ctx: Ctx, code: str, refs: list[str]) -> list[dict[str, Any]]:
    index = {e["id"]: e for e in ctx.state["evidence"]}
    start = ctx.patients[code]["start"]
    out = []
    for ref in refs:
        e = index.get(ref)
        if not e or e["code"] != code:
            continue
        day = int(re.match(r"Day (\d+)", e["at"]).group(1))  # type: ignore[union-attr]
        rid = f"{ctx.patients[code]['token']}@{day}" if ref[0] == "R" else str(det_id("event", ref))
        src = REPORTER.get(e["reporter"], REPORTER["System"])[0]
        out.append(
            {
                "kind": LETTER[ref[0]],
                "label": e["text"],
                "value": e["why"],
                "source": src,
                "citation": {
                    "ref_type": ref[0],
                    "ref_id": rid,
                    "label": f"{ref} {e['text']}",
                    "sim_day": day,
                },
            }
        )
        _ = start
    return out


def _spec(ctx: Ctx, src: str, code: str, **kw: Any) -> dict[str, Any]:
    p = ctx.patients[code]
    channel = kw.pop("channel", "telegram")
    recipients = [{"person_id": str(p["person_id"]), "token": p["token"], "channel": channel}]
    if kw.pop("with_supporter", False) and p.get("supporter_id"):
        recipients.append(
            {"person_id": str(p["supporter_id"]), "token": "S-01", "channel": "web_inbox"}
        )
    refs = kw.pop("refs", [])
    decision = kw.pop("decision", None)
    payload = {
        "audience": "patient",
        "title": kw.pop("title"),
        "channel": channel,
        "recipients": recipients,
        "body": kw.pop("body"),
        "subkind": kw.pop("subkind", "outreach"),
        "data": kw.pop("data", {}),
    }
    created = kw.pop("created_at")
    return {
        "src": src,
        "code": code,
        "tier": kw.pop("tier"),
        "payload": payload,
        "created_at": created,
        "due_at": kw.pop("due_at", created + timedelta(hours=4)),
        "evidence": evidence_items(ctx, code, refs),
        "decision": decision,
        "refs": refs,
    }


def build_specs(ctx: Ctx) -> list[dict[str, Any]]:
    st = ctx.state
    msgs = {ALIAS.get(m["srcId"], m["srcId"]): m for m in st["messages"]}
    specs: list[dict[str, Any]] = []
    for a in st["approvals"]:
        if not ctx.keep(a["patientCode"]):
            continue
        d = _decision_of(ctx, a, msgs.get(a["id"]))
        specs.append(
            _spec(
                ctx,
                a["id"],
                a["patientCode"],
                tier=a["lane"],
                title=a["title"],
                body=a["draft"],
                data={"why": a.get("why", ""), "refs": a.get("refs", [])},
                refs=a.get("refs", []),
                created_at=ctx.sim_now - timedelta(hours=2),
                due_at=ctx.sim_now + timedelta(minutes=a.get("dueMin", 240)),
                decision=d,
            )
        )
    for r in st["requests"]:
        if not ctx.keep(r["patientCode"]):
            continue
        start = ctx.patients[r["patientCode"]]["start"]
        created = parse_when(r["when"], ctx, start)
        d = _decision_of(ctx, r, msgs.get(r["id"]))
        data = {
            "kind": r["kind"],
            "text": r["text"],
            "refs": r.get("refs", []),
            "archived": bool(r.get("archived")),
        }
        specs.append(
            _spec(
                ctx,
                r["id"],
                r["patientCode"],
                tier="green",
                title=f"Patient request: {r['kind']}",
                body=r["draft"],
                subkind="patient_request",
                channel="web_inbox",
                data=data,
                refs=r.get("refs", []),
                created_at=created,
                due_at=ctx.sim_now + timedelta(minutes=r.get("dueMin", 240)),
                decision=d,
            )
        )
    specs += _old_message_specs(ctx, msgs)
    specs += _patient_app_specs(ctx)
    return specs


def _decision_of(
    ctx: Ctx, item: dict[str, Any], msg: dict[str, Any] | None
) -> dict[str, Any] | None:
    if item["status"] == "waiting":
        return None
    start = ctx.patients[item["patientCode"]]["start"]
    if msg:
        return {
            "action": "edit" if msg["version"] == 2 else "approve",
            "at": parse_when(msg["at"], ctx, start),
            "seen": msg["status"] == "seen",
            "text": msg["text"],
        }
    # declined (or approved without a stored message): decided 2 hours after it was raised
    base = (
        parse_when(item.get("when", "today 08:00"), ctx, start)
        if "when" in item
        else ctx.sim_now - timedelta(hours=1)
    )
    return {
        "action": "reject" if item["status"] == "declined" else "approve",
        "at": base + timedelta(hours=2),
        "seen": True,
        "text": None,
        "reason": "Needs a phone call instead",
    }


def _old_message_specs(ctx: Ctx, msgs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for src, m in msgs.items():
        if not src.startswith("old-") or not ctx.keep(m["code"]):
            continue
        start = ctx.patients[m["code"]]["start"]
        at = parse_when(m["at"], ctx, start)
        original = m["text"].replace("Please ", "Kindly ") if m["version"] == 2 else m["text"]
        ch = "web_inbox" if m["channel"] == "Patient app" else "telegram"
        out.append(
            _spec(
                ctx,
                src,
                m["code"],
                tier="green",
                title="Message to patient",
                body=original,
                channel=ch,
                created_at=at - timedelta(hours=1),
                due_at=at,
                decision={
                    "action": "edit" if m["version"] == 2 else "approve",
                    "at": at,
                    "seen": m["status"] == "seen",
                    "text": m["text"],
                },
            )
        )
    return out


def _patient_app_specs(ctx: Ctx) -> list[dict[str, Any]]:
    if "PT-0142" not in ctx.patients:
        return []
    out = []
    for src, days_ago, title, text, for_sup in app.PATIENT_MESSAGES:
        at = ctx.sim_now - timedelta(days=days_ago, hours=1)
        out.append(
            _spec(
                ctx,
                src,
                "PT-0142",
                tier="green",
                title=title,
                body=text,
                channel="web_inbox",
                with_supporter=for_sup,
                data={"patient_title": title, "for_supporter": for_sup},
                created_at=at - timedelta(hours=1),
                due_at=at,
                decision={
                    "action": "approve",
                    "at": at,
                    "seen": src not in app.UNREAD_MESSAGES,
                    "text": text,
                },
            )
        )
    for src, text, when, status, reply in app.PAST_REQUESTS:
        weeks = int(re.match(r"(\d+) weeks", when).group(1))  # type: ignore[union-attr]
        at = ctx.sim_now - timedelta(weeks=weeks)
        out.append(
            _spec(
                ctx,
                src,
                "PT-0142",
                tier="green",
                title="Patient request: Other",
                body=reply or "Please call the clinic so we can talk about it.",
                subkind="patient_request",
                channel="web_inbox",
                data={"kind": "Other", "text": text, "refs": [], "archived": True},
                created_at=at,
                due_at=at + timedelta(hours=4),
                decision={
                    "action": "approve" if status == "approved" else "reject",
                    "at": at + timedelta(hours=2),
                    "seen": True,
                    "text": None,
                    "reason": "Needs a phone call instead",
                },
            )
        )
    return out


def apply_decision(ctx: Ctx, approval_id: UUID, d: dict[str, Any]) -> None:
    """Replay a historical decision through the single decision function at its original time."""
    clock.pin(d["at"])
    try:
        body = ReviewDecisionIn(
            action=d["action"],
            reason=d.get("reason") if d["action"] == "reject" else None,
            edited={"body": d["text"]} if d["action"] == "edit" else None,
        )
        out = decide(approval_id, body, via="console", actor_id=ctx.doctor_id, conn=ctx.conn)
    finally:
        clock.pin(ctx.sim_now)
    if d.get("seen") and out.outbox_ids:
        ctx.conn.execute(
            "UPDATE cm.outbox SET meta = meta || %s::jsonb WHERE outbox_id = ANY(%s)",
            (json.dumps({"seen_at": (d["at"] + timedelta(hours=1)).isoformat()}), out.outbox_ids),
        )


def seed_review(ctx: Ctx) -> None:
    specs = build_specs(ctx)
    for s in specs:
        if s["decision"]:
            s["created_at"] = min(s["created_at"], s["decision"]["at"] - timedelta(hours=1))
        aid = approvals_repo.upsert(
            {
                "approval_id": det_id("approval", s["src"]),
                "patient_id": ctx.patients[s["code"]]["patient_id"],
                "thread_id": s["src"],
                "interrupt_id": "seed",
                "tier": s["tier"],
                "kind": "needs_human",
                "payload": s["payload"],
                "evidence": s["evidence"],
                "created_at": s["created_at"],
                "due_at": s["due_at"],
                "expires_at": s["created_at"] + timedelta(hours=48),
            },
            conn=ctx.conn,
        )
        if s["decision"]:
            apply_decision(ctx, aid, s["decision"])
    ctx.bump("approvals", sum(1 for s in specs if s["payload"]["subkind"] != "patient_request"))
    ctx.bump("requests", sum(1 for s in specs if s["payload"]["subkind"] == "patient_request"))
    seed_audit(ctx)


def seed_audit(ctx: Ctx) -> None:
    n = 0
    for a in ctx.state["audit"]:
        code = a["code"]
        if code not in ctx.patients or re.search(r"Approved|Edited|Declined|Undid", a["action"]):
            continue
        p = ctx.patients[code]
        who = {"Assistant": ("system", "system"), "Patient": (p["token"], "patient")}.get(
            a["actor"], ("D-01", "doctor")
        )
        action = (
            "assistant.draft"
            if a["actor"] == "Assistant"
            else "patient.request"
            if a["actor"] == "Patient"
            else "consent.withdrawn"
        )
        note = "; ".join(
            x
            for x in (a["action"].split(": ", 1)[1] if ": " in a["action"] else None, a.get("note"))
            if x
        )
        at = parse_when(a["at"], ctx, p["start"])
        if ctx.conn.execute(
            "SELECT 1 FROM cm.audit_log WHERE action=%s AND thread_id IS NOT DISTINCT FROM %s "
            "AND at=%s AND actor=%s",
            (action, a.get("srcId"), at, who[0]),
        ).fetchone():
            continue
        ctx.conn.execute(
            "INSERT INTO cm.audit_log (at, actor, role, action, tool, patient_id, thread_id) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (at, who[0], who[1], action, note or None, p["patient_id"], a.get("srcId")),
        )
        n += 1
    ctx.bump("audit_new", n)


_ = at_local
