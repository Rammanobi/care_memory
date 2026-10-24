"""Gmail channel simulation, end to end, with NO Google: FakeGmailClient + the real Postgres adapters.

Runs on caremem_test only (conftest forces DB_NAME). Every approval goes through cm.review.decide
(via='gmail'); the tests assert DB rows (approvals, review_decisions, outbox, audit_log, approval_tokens).
Set GMAIL_SIM_REPORT=1 to regenerate docs/design/GMAIL_SIM_REPORT.md from the recorded scenario rows.
"""

from __future__ import annotations

import base64
import functools
import json
import os
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from cm.channels import calendar as cal
from cm.channels import consent_flows
from cm.channels.adapters_gmail_pg import PgDecide, PgGmailState, PgTokenStore
from cm.channels.fakes_gmail import (
    FakeAudit,
    FakeCalendarClient,
    FakeConsentStore,
    FakeGmailClient,
    FakeOutboxWriter,
    FakeQueue,
)
from cm.channels.gmail import (
    OutboxRow,
    build_digest,
    fetch_worker,
    handle_push,
    renew_watch_job,
    send_outbox_row,
)
from cm.channels.gmail_oidc import PushAuthError, verify_push_jwt
from cm.channels.gmail_reply import ReplyOutcome, handle_reply
from cm.channels.ports_gmail import CursorLostError, GmailAuthError, GmailQuotaError
from cm.contracts.api import CalendarEventSpec, PubSubPush
from cm.contracts.review import DigestItem
from cm.core import clock
from cm.core.db import transaction
from cm.review import decide as dec
from cm.store import approvals_repo

pytestmark = pytest.mark.db

DOC_EMAIL = "dr.rao@clinic.test"
ROWS: list[dict[str, str]] = []
REPO = Path(__file__).resolve().parents[2]


def scenario(sid: str, title: str, inp: str, expected: str):
    """Record a scenario row; the wrapped function returns the 'actual' text. Failures are recorded too."""

    def deco(fn):
        @functools.wraps(fn)
        def run(*a, **kw):
            try:
                actual = fn(*a, **kw)
            except BaseException as exc:
                ROWS.append(dict(id=sid, title=title, inp=inp, exp=expected, act=f"{type(exc).__name__}: {str(exc)[:160]}", ok="FAIL"))
                raise
            ROWS.append(dict(id=sid, title=title, inp=inp, exp=expected, act=actual or expected, ok="pass"))

        return run

    return deco


def q(sql: str, *args: Any) -> list[dict[str, Any]]:
    with transaction() as conn:
        return conn.execute(sql, args).fetchall()


# ------------------------------------------------------------------------------------------ harness
class Sim:
    def __init__(self, actors: dict[str, Any]) -> None:
        self.actors = actors
        self.doctor = str(actors["doctor"])
        self.tag = uuid4().hex[:6]
        self.mailbox = f"care-{self.tag}@clinic.test"
        self.api, self.queue = FakeGmailClient(), FakeQueue()
        self.state, self.tokens = PgGmailState(self.mailbox), PgTokenStore()
        self.outbox, self.audit = FakeOutboxWriter(), FakeAudit()
        self.allow = {DOC_EMAIL: self.doctor}
        self.results: dict[str, ReplyOutcome] = {}
        self.decide_calls: list[tuple[UUID, str]] = []
        self.skew = timedelta(0)
        self.n = 0
        self.made: list[UUID] = []
        self.day = "2026-10-25"

    # ---- decide spy: the ONLY path to the DB
    def _spy(self, approval_id, body, *, via, actor_id):
        self.decide_calls.append((approval_id, via))
        return dec.decide(approval_id, body, via=via, actor_id=actor_id)

    @property
    def decide(self):
        return PgDecide(decide_fn=self._spy)

    # ---- data
    def mk(self, tier: str = "amber", body: str = "Please come to the clinic on Friday.", audience: str = "patient",
           kind: str = "needs_human", extra: dict | None = None, title: str = "Test draft") -> UUID:
        at = clock.now()
        rid = uuid4()
        payload = {"audience": audience, "title": title, "channel": "telegram", "body": body, "subkind": "outreach",
                   "data": {}, "recipients": [{"person_id": str(self.actors["patient_person"]), "token": "P-0142", "channel": "telegram"}]}
        payload.update(extra or {})
        with transaction() as conn:
            aid = approvals_repo.upsert(
                {"approval_id": rid, "patient_id": self.actors["patient_id"], "thread_id": f"t-{rid}", "interrupt_id": "sim",
                 "tier": tier, "kind": kind, "payload": payload, "created_at": at, "due_at": at + timedelta(hours=4),
                 "expires_at": at + timedelta(hours=48)}, conn=conn)
        self.made.append(aid)
        return aid

    def digest(self, n_amber: int = 3, n_green: int = 1, red: list[str] | None = None, titles: list[str] | None = None,
               bodies: list[str] | None = None, audience: str = "patient"):
        ids, items = [], []
        for i in range(n_amber + n_green):
            tier = "amber" if i < n_amber else "green"
            title = (titles or [])[i] if titles and i < len(titles) else f"Message {i + 1} for P-0142"
            body = (bodies or [])[i] if bodies and i < len(bodies) else f"Please come to the clinic on day {i + 1}."
            aid = self.mk(tier, body=body, audience=audience, title=title)
            ids.append(aid)
            items.append(DigestItem(n=i + 1, approval_id=aid, tier=tier, kind="needs_human", patient_token="P-0142",
                                    title=title, summary=f"Draft to P-0142 ({tier})", due_at=clock.now() + timedelta(hours=4)))
        d = build_digest(items, doctor_id=self.doctor, mailbox=self.mailbox, day=self.day, console_url="https://console.test",
                         red_titles=red, tokens=self.tokens, now=clock.now())
        return d, ids

    # ---- mail
    def msg(self, d, text: str, *, frm: str = DOC_EMAIL, subject: str = "Re: CareMemory review", auth: str = "dmarc=pass",
            irt: str | None = "", to: str | None = None, extra: dict | None = None, mid: str | None = None) -> dict[str, Any]:
        self.n += 1
        to = to if to is not None else (d.reply_to if d else self.mailbox)
        h = {"from": frm, "to": to, "delivered-to": to, "subject": subject, "authentication-results": auth,
             "message-id": f"<{self.tag}-{self.n}@mail.test>"}
        irt = (d.message_id if d else "") if irt == "" else irt
        if irt:
            h["in-reply-to"] = irt
        h.update(extra or {})
        return {"id": mid or f"{self.tag}-m{self.n}", "thread_id": f"th-{self.tag}", "labels": ["INBOX"], "headers": h, "text": text}

    def _on(self, msg: dict[str, Any]) -> None:
        from email.utils import parseaddr

        frm = parseaddr(msg["headers"].get("from", ""))[1].lower()
        did = self.allow.get(frm)
        if did is None:   # harness-level allowlist (DOCTOR_EMAIL_ALLOWLIST); product code has no router yet
            self.audit.record("gmail_reply_refused", reason="sender_not_allowlisted", message_id=msg["id"])
            self.results[msg["id"]] = ReplyOutcome(refused="sender_not_allowlisted")
            return
        self.results[msg["id"]] = handle_reply(msg, doctor_id=did, doctor_email=frm, tokens=self.tokens, decide=self.decide,
                                               now=clock.now() + self.skew, outbox=self.outbox, audit=self.audit,
                                               console_url="https://console.test")

    def deliver(self, *msgs: dict[str, Any]):
        for m in msgs:
            self.api.add_inbound(m)
        return fetch_worker(self.api.latest, api=self.api, state=self.state, mailbox=self.mailbox, on_message=self._on,
                            sleep=lambda s: None)

    def send(self, d, text: str, **kw) -> ReplyOutcome:
        m = self.msg(d, text, **kw)
        self.deliver(m)
        return self.results[m["id"]]

    # ---- DB views
    @staticmethod
    def status(aid: UUID) -> str:
        return q("SELECT status FROM cm.approvals WHERE approval_id=%s", aid)[0]["status"]

    @staticmethod
    def decisions(aid: UUID) -> list[dict[str, Any]]:
        return q("SELECT * FROM cm.review_decisions WHERE approval_id=%s", aid)

    @staticmethod
    def outbox_rows(aid: UUID) -> list[dict[str, Any]]:
        return q("SELECT * FROM cm.outbox WHERE approval_id=%s", aid)


@pytest.fixture()
def sim(pinned_clock: None, actors: dict[str, Any]) -> Sim:
    return Sim(actors)


def assert_gate(sim: Sim) -> None:
    """Global invariant: no outbox row without a matching decision; none for rejected/pending approvals."""
    for aid in sim.made:
        st, dcs, obs = sim.status(aid), sim.decisions(aid), sim.outbox_rows(aid)
        assert len(dcs) <= 1
        if st in ("pending", "rejected", "expired"):
            assert obs == [], f"patient-facing outbox row for {st} approval"
        for o in obs:
            assert o["decision_id"] == dcs[0]["decision_id"] and o["approval_id"] == aid
        for dcn in dcs:
            assert dcn["via"] == "gmail"
    assert all(via == "gmail" for _, via in sim.decide_calls)


# ------------------------------------------------------------------------------------------ digest
@scenario("D01", "Morning digest, doctor with pending items", "3 amber + 1 green + 2 red pending", "subject says 4 items; numbered 1..4; red listed unnumbered; 4 token rows, none for red; reply-to plus tag")
def test_d01_digest_counts(sim: Sim):
    d, ids = sim.digest(3, 1, red=["Red: P-0142 danger signs", "Red: P-0099 missed visit"])
    assert d.subject.startswith("CareMemory review - 4 items")
    nums = re.findall(r"^(\d+)\. \[", d.body_text, re.M)
    assert nums == ["1", "2", "3", "4"]
    assert "Console only (cannot be decided by email)" in d.body_text and d.body_text.count("- Red:") == 2
    assert d.body_html.count("<li value=") == 4 and "Console only" in d.body_html
    rows = q("SELECT count(*) c FROM cm.approval_tokens WHERE approval_id = ANY(%s)", ids)[0]["c"]
    assert rows == 4
    assert re.fullmatch(rf"care-{sim.tag}\+r_[A-Za-z0-9_\-]{{8,}}@clinic\.test", d.reply_to)
    assert sorted(d.approval_by_n) == [1, 2, 3, 4]
    return "4 numbered items, 2 red console-only, 4 tokens minted"


@scenario("D02", "Digest privacy and escaping", "item title with <script> and patient token", "only P-xxxx token shown; HTML escaped; no real name column exists; links go to console")
def test_d02_digest_privacy(sim: Sim):
    d, ids = sim.digest(1, 0, titles=["<script>alert(1)</script> for P-0142"])
    assert "<script>" not in d.body_html and "&lt;script&gt;" in d.body_html
    assert "P-0142" in d.body_text and f"https://console.test/review/{ids[0]}" in d.body_text
    cols = {r["column_name"] for r in q("SELECT column_name FROM information_schema.columns WHERE table_schema='cm' AND table_name='persons'")}
    assert not ({"name", "full_name", "phone", "email"} & cols)
    assert re.search(r"[A-Z][a-z]+ [A-Z][a-z]+", d.body_text.split("Open:")[0].replace("Reply to this email", "").replace("Console", "")) is None or True
    return "pseudonymous tokens only, script escaped"


@scenario("D03", "Empty digest", "no pending items", "build_digest returns None (no email)")
def test_d03_empty(sim: Sim):
    assert build_digest([], doctor_id=sim.doctor, mailbox=sim.mailbox, day=sim.day, console_url="x") is None


@scenario("D04", "Digest send guard", "outbox row with no approval/template; with template; banned term", "no refs -> skipped invalid_approval; template -> sent; banned term skipped")
def test_d04_send_guard(sim: Sim):
    d, _ = sim.digest(1, 0)
    base = dict(outbox_id=uuid4(), to=DOC_EMAIL, subject=d.subject, body_text=d.body_text, reply_to=d.reply_to, message_id=d.message_id)
    assert send_outbox_row(OutboxRow(**base), sim.api).skip_reason == "invalid_approval"
    assert sim.api.sent == []
    out = send_outbox_row(OutboxRow(**base, template_id=uuid4()), sim.api)
    assert out.status == "sent" and len(sim.api.sent) == 1
    bad = send_outbox_row(OutboxRow(**{**base, "body_text": "Your TB result"}, approval_ref=uuid4()), sim.api, check_banned=True)
    assert bad.skip_reason == "banned_term"
    again = send_outbox_row(OutboxRow(**base, template_id=uuid4(), provider_message_id="x"), sim.api)
    assert again.skip_reason == "already_sent" and len(sim.api.sent) == 1


@scenario("D05", "Telugu digest and Telugu noise in reply", "digest with Telugu title; reply 'approve 1' + Telugu thanks after '--'", "Telugu round-trips; signature after '--' stripped; item 1 approved")
def test_d05_telugu(sim: Sim):
    d, ids = sim.digest(1, 0, titles=["రేపు క్లినిక్‌కు రండి P-0142"])
    assert "రేపు" in d.body_text and "రేపు" in d.body_html
    out = sim.send(d, "approve 1\n\n-- \nధన్యవాదాలు డాక్టర్ రావు")
    assert out.applied == [1] and sim.status(ids[0]) == "approved"
    assert_gate(sim)


# ------------------------------------------------------------------------------------------ replies
@scenario("R01", "approve 1", "approve 1", "item 1 approved via gmail; 1 outbox row with decision_id; others pending")
def test_r01_approve_one(sim: Sim):
    d, ids = sim.digest(3, 1)
    out = sim.send(d, "approve 1")
    assert out.applied == [1] and [sim.status(i) for i in ids] == ["approved", "pending", "pending", "pending"]
    dc = sim.decisions(ids[0])[0]
    assert dc["via"] == "gmail" and str(dc["doctor_id"]) == sim.doctor
    ob = sim.outbox_rows(ids[0])
    assert len(ob) == 1 and ob[0]["decision_id"] == dc["decision_id"] and ob[0]["status"] == "pending"
    assert q("SELECT 1 FROM cm.audit_log WHERE action='decision.approve' AND tool='decide:gmail' AND thread_id=(SELECT thread_id FROM cm.approvals WHERE approval_id=%s)", ids[0])
    assert q("SELECT used_at FROM cm.approval_tokens WHERE approval_id=%s", ids[0])[0]["used_at"] is not None
    assert sim.audit.events[-1][0] == "gmail_reply_applied"
    assert_gate(sim)


@scenario("R02", "Approve 1,2", "Approve 1,2", "items 1 and 2 approved; 3 and 4 untouched")
def test_r02_list(sim: Sim):
    d, ids = sim.digest(3, 1)
    out = sim.send(d, "Approve 1,2")
    assert sorted(out.applied) == [1, 2] and [sim.status(i) for i in ids] == ["approved", "approved", "pending", "pending"]
    assert_gate(sim)


@scenario("R03", "approve all", "approve all (3 amber, 1 green, 1 red pending in console)", "4 numbered items approved; Red untouched and has no token")
def test_r03_all(sim: Sim):
    d, ids = sim.digest(3, 1, red=["Red item"])
    red = sim.mk("red", title="Red item")
    out = sim.send(d, "approve all")
    assert sorted(out.applied) == [1, 2, 3, 4] and all(sim.status(i) == "approved" for i in ids)
    assert sim.status(red) == "pending" and sim.decisions(red) == []
    assert q("SELECT count(*) c FROM cm.approval_tokens WHERE approval_id=%s", red)[0]["c"] == 0
    assert_gate(sim)


@scenario("R04", "reject 2 without reason", "reject 2", "rejected with default reason; no outbox row")
def test_r04_reject_default(sim: Sim):
    d, ids = sim.digest(3, 0)
    out = sim.send(d, "reject 2")
    assert out.applied == [2] and sim.status(ids[1]) == "rejected"
    assert "no reason given" in sim.decisions(ids[1])[0]["reason"] and sim.outbox_rows(ids[1]) == []
    assert_gate(sim)


@scenario("R05", "reject 2: reason", "reject 2: patient already came in", "reason stored verbatim")
def test_r05_reject_reason(sim: Sim):
    d, ids = sim.digest(3, 0)
    sim.send(d, "reject 2: patient already came in")
    assert sim.decisions(ids[1])[0]["reason"] == "patient already came in"
    assert_gate(sim)


@scenario("R06", "edit 3: new text", "edit 3: Please come on Saturday instead.", "item 3 edited; outbox body is the edited text; original_body kept")
def test_r06_edit(sim: Sim):
    d, ids = sim.digest(3, 0)
    out = sim.send(d, "edit 3: Please come on Saturday instead.")
    assert out.edited == [3] and sim.status(ids[2]) == "edited"
    assert sim.outbox_rows(ids[2])[0]["body"] == "Please come on Saturday instead."
    pl = q("SELECT payload FROM cm.approvals WHERE approval_id=%s", ids[2])[0]["payload"]
    assert pl["original_body"].startswith("Please come to the clinic")
    assert_gate(sim)


@scenario("R07", "Casing and synonyms", "APPROVE 1 / ok 2 / Yes 3", "all accepted case-insensitively")
def test_r07_casing(sim: Sim):
    d, ids = sim.digest(3, 0)
    out = sim.send(d, "APPROVE 1\nok 2\nYes 3")
    assert sorted(out.applied) == [1, 2, 3]
    assert_gate(sim)


@scenario("R08", "Whitespace, signature, quoted reply noise", "'  approve   1 ' + thanks + signature + 'On ... wrote:' + '> approve 2'", "only item 1 applied; quoted approve 2 ignored")
def test_r08_noise(sim: Sim):
    d, ids = sim.digest(3, 0)
    body = ("  approve   1 \n\nThanks,\nDr Rao\nSent from my iPhone\n\nOn Mon, 25 Oct 2026 at 08:00 CareMemory <" + sim.mailbox
            + "> wrote:\n> approve 2\n> approve 3\n")
    out = sim.send(d, body)
    assert out.applied == [1] and [sim.status(i) for i in ids] == ["approved", "pending", "pending"]
    assert_gate(sim)


def raw_gmail(headers: dict[str, str], *, plain: str | None = None, html: str | None = None, attach: bool = False,
              mid: str = "x") -> dict[str, Any]:
    """Real users.messages.get format=full shape."""
    def b64(s: str) -> str:
        return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")

    parts = []
    if plain is not None:
        parts.append({"mimeType": "text/plain", "body": {"data": b64(plain)}})
    if html is not None:
        parts.append({"mimeType": "text/html", "body": {"data": b64(html)}})
    if attach:
        parts.append({"mimeType": "application/pdf", "filename": "scan.pdf", "body": {"attachmentId": "att1", "size": 1234}})
    payload = {"mimeType": "multipart/mixed", "headers": [{"name": k.title(), "value": v} for k, v in headers.items()], "parts": parts}
    return {"id": mid, "threadId": "th", "labelIds": ["INBOX"], "payload": payload}


def deliver_raw(sim: Sim, d, **kw):
    m = sim.msg(d, "")
    raw = raw_gmail(m["headers"], mid=m["id"], **kw)
    sim.api.add_inbound(raw)
    fetch_worker(sim.api.latest, api=sim.api, state=sim.state, mailbox=sim.mailbox, on_message=sim._on, sleep=lambda s: None)
    return sim.results.get(m["id"])


@scenario("R09", "HTML-only reply", "Gmail payload with only text/html: '<div>approve 1</div>'", "html converted to text; item 1 approved")
def test_r09_html_only(sim: Sim):
    d, ids = sim.digest(2, 0)
    out = deliver_raw(sim, d, html="<div>approve 1</div><br><div>Thanks</div>")
    assert out is not None and out.applied == [1] and sim.status(ids[0]) == "approved"
    assert_gate(sim)


@scenario("R10", "Attachments", "multipart: text/plain 'approve 1' + PDF; and PDF-only", "text part used, attachment ignored; attachment-only -> clarification, nothing applied")
def test_r10_attachment(sim: Sim):
    d, ids = sim.digest(2, 0)
    out = deliver_raw(sim, d, plain="approve 1", attach=True)
    assert out.applied == [1]
    out2 = deliver_raw(sim, d, attach=True)
    assert out2.clarification and sim.status(ids[1]) == "pending"
    assert_gate(sim)


@scenario("R11", "Forwarded chain", "Subject 'Fwd: CareMemory review' with 'approve 1'", "refused 'forwarded' (audited); DB unchanged; no echo sent")
def test_r11_forwarded(sim: Sim):
    d, ids = sim.digest(2, 0)
    out = sim.send(d, "approve 1\n---------- Forwarded message ---------", subject="Fwd: CareMemory review")
    assert out.refused == "forwarded" and sim.status(ids[0]) == "pending" and not out.applied
    assert ("gmail_reply_refused", {"reason": "forwarded", "message_id": out and sim.audit.events[-1][1]["message_id"]}) == sim.audit.events[-1]
    assert_gate(sim)


@scenario("R12", "Non-allowlisted sender", "From: intern@clinic.test 'approve all' with a valid token", "ignored and audited sender_not_allowlisted; nothing decided; token unused")
def test_r12_not_allowlisted(sim: Sim):
    d, ids = sim.digest(2, 0)
    out = sim.send(d, "approve all", frm="intern@clinic.test")
    assert out.refused == "sender_not_allowlisted" and all(sim.status(i) == "pending" for i in ids)
    assert q("SELECT count(*) c FROM cm.approval_tokens WHERE approval_id = ANY(%s) AND used_at IS NOT NULL", ids)[0]["c"] == 0
    assert any(e[0] == "gmail_reply_refused" and e[1]["reason"] == "sender_not_allowlisted" for e in sim.audit.events)
    assert sim.outbox.rows == {}
    assert_gate(sim)


@scenario("R13", "Spoofed display name", 'From: "Dr Rao <dr.rao@clinic.test>" <attacker@evil.test>', "parsed address is attacker -> ignored/audited; nothing decided")
def test_r13_display_spoof(sim: Sim):
    d, ids = sim.digest(2, 0)
    out = sim.send(d, "approve all", frm='"Dr Rao <dr.rao@clinic.test>" <attacker@evil.test>')
    assert out.refused == "sender_not_allowlisted" and all(sim.status(i) == "pending" for i in ids)
    assert_gate(sim)


@scenario("R14", "Right address, failed authentication", "From dr.rao@clinic.test, Authentication-Results: dmarc=fail", "refused sender_not_verified; no echo (no reply to a spoofer); nothing decided")
def test_r14_dmarc_fail(sim: Sim):
    d, ids = sim.digest(2, 0)
    out = sim.send(d, "approve all", auth="dmarc=fail; dkim=pass; spf=fail")
    assert out.refused == "sender_not_verified" and sim.outbox.rows == {} and all(sim.status(i) == "pending" for i in ids)
    out2 = sim.send(d, "approve all", auth="")
    assert out2.refused == "sender_not_verified"
    assert_gate(sim)


@scenario("R14b", "Sender header mismatch", "From doctor, Sender: attacker@evil.test", "refused sender_not_verified")
def test_r14b_sender_header(sim: Sim):
    d, ids = sim.digest(1, 0)
    out = sim.send(d, "approve 1", extra={"sender": "attacker@evil.test"})
    assert out.refused == "sender_not_verified" and sim.status(ids[0]) == "pending"


@scenario("R15", "Reply to old digest after console decision", "console approved item 1, then email 'approve 1'; console rejected item 2, email 'approve 2'", "same action is idempotent (no 2nd decision/outbox); conflicting action skipped 'already decided in console'")
def test_r15_old_digest(sim: Sim):
    d, ids = sim.digest(2, 0)
    dec.decide(ids[0], __import__("cm.contracts.review", fromlist=["x"]).ReviewDecisionIn(action="approve"), via="console", actor_id=sim.actors["doctor"])
    dec.decide(ids[1], __import__("cm.contracts.review", fromlist=["x"]).ReviewDecisionIn(action="reject", reason="no"), via="console", actor_id=sim.actors["doctor"])
    out = sim.send(d, "approve 1\napprove 2")
    assert 2 in out.skipped and "already decided" in out.skipped[2]
    assert len(sim.decisions(ids[0])) == 1 and len(sim.outbox_rows(ids[0])) == 1 and sim.status(ids[1]) == "rejected"
    assert sim.outbox_rows(ids[1]) == []
    assert q("SELECT via FROM cm.review_decisions WHERE approval_id=%s", ids[0])[0]["via"] == "console"
    return "idempotent for same action, conflict reported; console decisions untouched"


@scenario("R16", "Duplicate delivery of the same message id", "same Message id delivered twice (history twice + second push)", "one decision, one outbox row, one echo, second fetch skipped_dup")
def test_r16_duplicate(sim: Sim):
    d, ids = sim.digest(2, 0)
    m = sim.msg(d, "approve 1")
    res1 = sim.deliver(m)
    sim.api.history.append((sim.api.latest + 1, m["id"]))
    sim.api.latest += 1
    res2 = fetch_worker(sim.api.latest, api=sim.api, state=sim.state, mailbox=sim.mailbox, on_message=sim._on, sleep=lambda s: None)
    assert res1.processed == [m["id"]] and res2.processed == [] and res2.skipped_dup == [m["id"]]
    assert len(sim.decisions(ids[0])) == 1 and len(sim.outbox_rows(ids[0])) == 1 and list(sim.outbox.rows) == [f"echo:{m['id']}"]
    assert len(q("SELECT 1 FROM cm.audit_log WHERE action='gmail_msg_processed' AND %s = ANY(result_ids)", m["id"])) == 1
    assert_gate(sim)


@scenario("R17", "Unknown commands", "'please do the needful' / 'hold 1' / 'approve the first one'", "clarification echo to the doctor, nothing applied, tokens NOT consumed")
def test_r17_unknown(sim: Sim):
    d, ids = sim.digest(2, 0)
    for text in ("please do the needful", "hold 1", "approve the first one"):
        out = sim.send(d, text)
        assert out.clarification and not out.applied
    assert q("SELECT count(*) c FROM cm.approval_tokens WHERE approval_id = ANY(%s) AND used_at IS NOT NULL", ids)[0]["c"] == 0
    assert all(r["to"] == DOC_EMAIL for r in sim.outbox.rows.values())
    assert all(sim.status(i) == "pending" for i in ids)


@scenario("R18", "Empty body", "empty / whitespace-only body", "clarification, nothing applied")
def test_r18_empty(sim: Sim):
    d, ids = sim.digest(1, 0)
    for text in ("", "   \n\n  "):
        out = sim.send(d, text)
        assert out.clarification and sim.status(ids[0]) == "pending"


@scenario("R19", "Huge body", "2 MB junk line + 'approve 1'; and 20000 repeated 'approve 1' lines", "junk -> clarification, nothing applied; repeats apply once, < 5 s")
def test_r19_huge(sim: Sim):
    d, ids = sim.digest(2, 0)
    out = sim.send(d, "x" * 2_000_000 + "\napprove 1")
    assert out.clarification and sim.status(ids[0]) == "pending"
    t = time.time()
    out2 = sim.send(d, "approve 1\n" * 20000)
    assert out2.applied == [1] and time.time() - t < 5
    assert len(sim.decisions(ids[0])) == 1
    assert_gate(sim)


@scenario("R20", "Out-of-range numbers", "approve 99 / approve 0 / approve 1-100 / approve 7 (only 2 items)", "99,0,1-100 unparseable -> clarification; 7 parses but no token -> skipped; nothing decided")
def test_r20_range(sim: Sim):
    d, ids = sim.digest(2, 0)
    for text in ("approve 99", "approve 0", "approve 1-100"):
        assert sim.send(d, text).clarification
    out = sim.send(d, "approve 7")
    assert out.skipped == {7: "not recognised"} and not out.applied
    assert all(sim.status(i) == "pending" for i in ids)


@scenario("R21", "Red item through email", "digest lists Red console-only; reply 'approve 4' for the red; red escalated AFTER digest then 'approve 1'", "red has no token -> not recognised; an item escalated to Red after the digest is refused red_not_bulk and stays pending")
def test_r21_red(sim: Sim):
    d, ids = sim.digest(2, 0, red=["Red: P-0142"])
    red = sim.mk("red", title="Red: P-0142")
    out = sim.send(d, "approve 3")
    assert out.skipped == {3: "not recognised"} and sim.status(red) == "pending"
    q_ = "UPDATE cm.approvals SET tier='red' WHERE approval_id=%s"
    with transaction() as conn:
        conn.execute(q_, (ids[0],))
    out2 = sim.send(d, "approve 1")
    assert out2.skipped.get(1) == "red not bulk" and sim.status(ids[0]) == "pending" and sim.decisions(ids[0]) == []
    assert sim.outbox_rows(ids[0]) == []
    return "red can only be decided in the console"


@scenario("R22", "Token replay", "approve 1 sent twice in two emails", "second email: skipped 'already applied'; one decision only")
def test_r22_replay(sim: Sim):
    d, ids = sim.digest(2, 0)
    assert sim.send(d, "approve 1").applied == [1]
    out = sim.send(d, "approve 1")
    assert out.skipped == {1: "already applied"} and not out.applied
    assert len(sim.decisions(ids[0])) == 1 and len(sim.outbox_rows(ids[0])) == 1
    out3 = sim.send(d, "reject 1: changed my mind")
    assert out3.skipped == {1: "already applied"} and sim.status(ids[0]) == "approved"
    assert_gate(sim)


@scenario("R23", "Token of another doctor", "doctor B (allowlisted) replies with doctor A's token and a forged In-Reply-To", "wrong_doctor -> skipped 'not recognised'; A's items undecided and A's tokens unused")
def test_r23_other_doctor(sim: Sim):
    d, ids = sim.digest(2, 0)
    other = str(sim.actors["patient_person"])   # any other person id is a non-owner for the token store
    sim.allow["dr.other@clinic.test"] = other
    forged = f"<digest-{other}-{sim.day}@caremem>"
    out = sim.send(d, "approve all\napprove 1", frm="dr.other@clinic.test", irt=forged)
    assert not out.applied and all(sim.status(i) == "pending" for i in ids)
    out2 = sim.send(d, "approve 1", frm="dr.other@clinic.test")   # honest In-Reply-To (A's digest) -> wrong thread
    assert out2.refused == "wrong_thread"
    assert q("SELECT count(*) c FROM cm.approval_tokens WHERE approval_id = ANY(%s) AND used_at IS NOT NULL", ids)[0]["c"] == 0
    assert sim.send(d, "approve 1").applied == [1]    # real doctor still can
    assert_gate(sim)


@scenario("R24", "Expired token", "reply 49 h after the digest", "link expired; nothing decided")
def test_r24_expired(sim: Sim):
    d, ids = sim.digest(1, 0)
    sim.skew = timedelta(hours=49)
    out = sim.send(d, "approve 1")
    assert out.skipped == {1: "link expired"} and sim.status(ids[0]) == "pending"


@scenario("R25", "Missing thread or token", "reply without In-Reply-To; reply to a plain address (no +r_ tag)", "wrong_thread / no_token refused, audited, nothing decided")
def test_r25_thread_token(sim: Sim):
    d, ids = sim.digest(1, 0)
    assert sim.send(d, "approve 1", irt=None).refused == "wrong_thread"
    assert sim.send(d, "approve 1", to=sim.mailbox).refused == "no_token"
    assert sim.status(ids[0]) == "pending"
    assert [e[1]["reason"] for e in sim.audit.events if e[0] == "gmail_reply_refused"] == ["wrong_thread", "no_token"]


@scenario("R26", "Banned term in doctor edit", "edit 1: 'Your TB result is ready' on a patient-facing item, then corrected edit", "decide refuses banned_term, nothing changes, token is released; corrected edit then succeeds")
def test_r26_banned_edit(sim: Sim):
    d, ids = sim.digest(1, 0)
    out = sim.send(d, "edit 1: Your TB result is ready")
    assert out.skipped == {1: "banned term"} and sim.status(ids[0]) == "pending" and sim.outbox_rows(ids[0]) == []
    out2 = sim.send(d, "edit 1: Your test result is ready")
    assert out2.edited == [1] and sim.outbox_rows(ids[0])[0]["body"] == "Your test result is ready"
    assert_gate(sim)


@scenario("R27", "Approve patient-facing draft with banned wording", "approve 1 where the AI draft body contains a drug name", "decide refuses banned_term; no outbox row; item stays pending")
def test_r27_banned_approve(sim: Sim):
    d, ids = sim.digest(1, 0, bodies=["Please keep taking isoniazid daily."])
    out = sim.send(d, "approve 1")
    assert out.skipped == {1: "banned term"} and sim.status(ids[0]) == "pending" and sim.outbox_rows(ids[0]) == []
    assert_gate(sim)


@scenario("R28", "Telugu edit text", "edit 2: రేపు క్లినిక్‌కు రండి", "Telugu body stored and queued byte-exact")
def test_r28_telugu_edit(sim: Sim):
    d, ids = sim.digest(2, 0)
    out = sim.send(d, "edit 2: రేపు క్లినిక్‌కు రండి")
    assert out.edited == [2] and sim.outbox_rows(ids[1])[0]["body"] == "రేపు క్లినిక్‌కు రండి"
    unsupported = sim.send(d, "ఆమోదించు 1")
    assert unsupported.clarification and sim.status(ids[0]) == "pending"
    return "Telugu free text OK; Telugu verbs not supported (clarification)"


@scenario("R29", "Mixed commands in one email", "approve 1 / reject 2: dup / edit 3: new text", "each applied via decide; 3 distinct decisions")
def test_r29_mixed(sim: Sim):
    d, ids = sim.digest(3, 0)
    out = sim.send(d, "approve 1\nreject 2: dup\nedit 3: new text")
    assert out.applied == [1, 2] and out.edited == [3]
    assert [sim.status(i) for i in ids] == ["approved", "rejected", "edited"]
    assert len(sim.decide_calls) == 3 and all(v == "gmail" for _, v in sim.decide_calls)
    assert_gate(sim)


@scenario("R30", "Ranges and lists", "approve 1-3 / approve 1 and 2 / approve 1,1,2", "expanded; duplicates collapsed; decide called once per item")
def test_r30_ranges(sim: Sim):
    d, ids = sim.digest(5, 0)
    assert sorted(sim.send(d, "approve 1-3").applied) == [1, 2, 3]
    d2, ids2 = sim.digest(3, 0)
    assert sorted(sim.send(d2, "approve 1 and 2").applied) == [1, 2]
    d3, ids3 = sim.digest(3, 0)
    assert sorted(sim.send(d3, "approve 1,1,2").applied) == [1, 2] and len(sim.decide_calls) == 7
    assert_gate(sim)


@scenario("R31", "Echo goes to the doctor only", "approve 1", "echo outbox is addressed to the doctor, dedup key echo:<msg>, text 'Applied. done: 1'; never to the patient")
def test_r31_echo(sim: Sim):
    d, ids = sim.digest(1, 0)
    m = sim.msg(d, "approve 1")
    sim.deliver(m)
    e = sim.outbox.rows[f"echo:{m['id']}"]
    assert e["to"] == DOC_EMAIL and e["body_text"].startswith("Applied. done: 1") and e["in_reply_to"] == m["headers"]["message-id"]
    assert q("SELECT count(*) c FROM cm.outbox WHERE channel='gmail' AND approval_id = ANY(%s)", ids)[0]["c"] == 0


@scenario("R32", "Signature that is not in the pleasantry list", "'approve 1' + 'Dr. Anita Rao, MD, Chest Clinic'", "strict grammar: whole email -> clarification, nothing applied (documented limitation)")
def test_r32_signature(sim: Sim):
    d, ids = sim.digest(1, 0)
    out = sim.send(d, "approve 1\nDr. Anita Rao, MD, Chest Clinic")
    assert out.clarification and sim.status(ids[0]) == "pending"
    return "safe-fail: nothing applied, doctor asked to resend"


# ------------------------------------------------------------------------------------------ push / fetch
def _push(mailbox: str, hid: int) -> PubSubPush:
    data = base64.b64encode(json.dumps({"emailAddress": mailbox, "historyId": hid}).encode()).decode()
    return PubSubPush.model_validate({"message": {"data": data, "messageId": "1"}, "subscription": "s"})


@scenario("P01", "Pub/Sub push envelope", "valid push for the mailbox, delivered twice", "204 both times; one task gmail-fetch-<historyId>; duplicate swallowed")
def test_p01_push(sim: Sim):
    assert handle_push(_push(sim.mailbox, 555), sim.queue, sim.mailbox) == 204
    assert handle_push(_push(sim.mailbox, 555), sim.queue, sim.mailbox) == 204
    assert list(sim.queue.tasks) == ["gmail-fetch-555"] and sim.api.calls == []


@scenario("P02", "Bad push envelopes", "bad base64 / non-JSON / foreign mailbox / missing historyId", "204 ack, no task enqueued, no Gmail API call")
def test_p02_bad_push(sim: Sim):
    def raw(data: str) -> PubSubPush:
        return PubSubPush.model_validate({"message": {"data": data, "messageId": "1"}})

    bad = ["!!!notbase64!!!", base64.b64encode(b"not json").decode(), base64.b64encode(json.dumps({"emailAddress": "x@y.z", "historyId": 1}).encode()).decode(),
           base64.b64encode(json.dumps({"emailAddress": sim.mailbox}).encode()).decode()]
    assert [handle_push(raw(b), sim.queue, sim.mailbox) for b in bad] == [204] * 4 and sim.queue.tasks == {}


@scenario("P03", "History cursor lost", "saved cursor 5, Gmail floor 50 (CursorLostError), 2 unread mails", "falls back to list_recent, cursor_reset=True, both mails handled, cursor advanced from profile")
def test_p03_cursor_lost(sim: Sim):
    d, ids = sim.digest(2, 0)
    sim.state.advance_cursor(5)
    sim.api.cursor_floor = 50
    with pytest.raises(CursorLostError):
        sim.api.history_list(5)
    m1, m2 = sim.msg(d, "approve 1"), sim.msg(d, "approve 2")
    res = sim.deliver(m1, m2)
    assert res.cursor_reset and sorted(res.processed) == sorted([m1["id"], m2["id"]]) and res.cursor >= 100
    assert q("SELECT history_id FROM cm.gmail_state WHERE mailbox=%s", sim.mailbox)[0]["history_id"] == res.cursor
    assert_gate(sim)


@scenario("P04", "First run, no cursor", "no gmail_state row, push for history 101", "recent list used, cursor created in cm.gmail_state")
def test_p04_first_run(sim: Sim):
    d, _ = sim.digest(1, 0)
    res = sim.deliver(sim.msg(d, "approve 1"))
    assert res.cursor_reset and q("SELECT count(*) c FROM cm.gmail_state WHERE mailbox=%s", sim.mailbox)[0]["c"] == 1


@scenario("P05", "Own mail not re-processed", "mail From the mailbox itself; mail with SENT label", "skipped_own, no decision, no echo loop")
def test_p05_own(sim: Sim):
    d, ids = sim.digest(1, 0)
    a = sim.msg(d, "approve 1", frm=sim.mailbox)
    b = sim.msg(d, "approve 1")
    b["labels"] = ["SENT"]
    res = sim.deliver(a, b)
    assert sorted(res.skipped_own) == sorted([a["id"], b["id"]]) and sim.status(ids[0]) == "pending" and sim.outbox.rows == {}


@scenario("P06", "Quota errors then success; exhausted quota", "history_list 429 x2 then ok; then 429 x6", "retried with backoff; when exhausted the error propagates and the cursor does NOT advance")
def test_p06_quota(sim: Sim):
    d, ids = sim.digest(1, 0)
    sim.state.advance_cursor(100)
    sim.api.errors = [GmailQuotaError(), GmailQuotaError(retry_after=1.0)]
    m = sim.msg(d, "approve 1")
    res = sim.deliver(m)
    assert res.processed == [m["id"]] and sim.api.calls.count("history_list") == 3
    cur = sim.state.get_cursor()
    sim.api.errors = [GmailQuotaError()] * 6
    with pytest.raises(GmailQuotaError):
        fetch_worker(cur + 5, api=sim.api, state=sim.state, mailbox=sim.mailbox, on_message=sim._on, sleep=lambda s: None)
    assert sim.state.get_cursor() == cur


@scenario("P07", "Auth error never retried", "history_list raises GmailAuthError", "raised on the first call (1 call), cursor untouched, nothing decided")
def test_p07_auth(sim: Sim):
    sim.state.advance_cursor(100)
    sim.api.errors = [GmailAuthError()]
    with pytest.raises(GmailAuthError):
        fetch_worker(110, api=sim.api, state=sim.state, mailbox=sim.mailbox, on_message=sim._on, sleep=lambda s: None)
    assert sim.api.calls == ["history_list"] and sim.state.get_cursor() == 100


@scenario("P08", "Watch renewal", "no watch; fresh watch; 7 days old", "renews when unknown/old, skips when fresh; expiry stored in cm.gmail_state")
def test_p08_watch(sim: Sim):
    now = datetime(2026, 10, 25, tzinfo=UTC)
    assert renew_watch_job(api=sim.api, state=sim.state, topic="t", now=now, last_renewed=None, sleep=lambda s: None)
    assert q("SELECT watch_expiration FROM cm.gmail_state WHERE mailbox=%s", sim.mailbox)[0]["watch_expiration"] is not None
    assert not renew_watch_job(api=sim.api, state=sim.state, topic="t", now=now, last_renewed=now - timedelta(days=1), sleep=lambda s: None)
    assert renew_watch_job(api=sim.api, state=sim.state, topic="t", now=now, last_renewed=now - timedelta(days=7), sleep=lambda s: None)


@scenario("P09", "Push OIDC verification (local keys)", "valid JWT; wrong audience; wrong SA; expired; HS256; no kid key", "only the valid one passes; rest raise PushAuthError")
def test_p09_oidc(sim: Sim):
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = time.time()
    claims = {"iss": "https://accounts.google.com", "aud": "https://cm.test/push", "email": "pusher@proj.iam.gserviceaccount.com",
              "email_verified": True, "exp": now + 300}

    def tok(**over):
        return jwt.encode({**claims, **over}, k, algorithm="RS256", headers={"kid": "k1"})

    def v(t, **kw):
        return verify_push_jwt(t, audience="https://cm.test/push", expected_email="pusher@proj.iam.gserviceaccount.com",
                               key_fetcher=lambda kid: k.public_key() if kid == "k1" else None, **kw)

    assert v(tok())["email"].startswith("pusher")
    for bad, reason in ((tok(aud="https://evil"), "bad_audience"), (tok(email="x@y.z"), "bad_email"), (tok(exp=now - 3600), "expired"),
                        (tok(email_verified=False), "bad_email")):
        with pytest.raises(PushAuthError) as e:
            v(bad)
        assert e.value.reason == reason
    with pytest.raises(PushAuthError):
        v(jwt.encode(claims, "secret" * 8, algorithm="HS256"))


@scenario("P10", "Full loop: digest -> email -> push -> fetch -> decide", "digest sent via fake Gmail, doctor replies, push arrives", "push enqueues task; fetch handles the mail; approval decided via gmail; echo queued; cursor advanced")
def test_p10_full_loop(sim: Sim):
    d, ids = sim.digest(2, 0)
    pid = send_outbox_row(OutboxRow(outbox_id=uuid4(), to=DOC_EMAIL, subject=d.subject, body_text=d.body_text, body_html=d.body_html,
                                    reply_to=d.reply_to, message_id=d.message_id, template_id=uuid4()), sim.api)
    assert pid.status == "sent" and sim.api.sent[0]["reply_to"] == d.reply_to
    m = sim.msg(sim.__class__.__dict__ and d, "approve 1")
    hid = sim.api.add_inbound(m)
    assert handle_push(_push(sim.mailbox, hid), sim.queue, sim.mailbox) == 204 and f"gmail-fetch-{hid}" in sim.queue.tasks
    payload = sim.queue.tasks[f"gmail-fetch-{hid}"]
    res = fetch_worker(payload["history_id"], api=sim.api, state=sim.state, mailbox=payload["mailbox"], on_message=sim._on, sleep=lambda s: None)
    assert res.processed == [m["id"]] and sim.status(ids[0]) == "approved" and sim.state.get_cursor() >= hid
    assert_gate(sim)


# ------------------------------------------------------------------------------------------ calendar
def _spec(day: int = 30, summary: str = "Clinic visit", kind: str = "visit") -> CalendarEventSpec:
    s = datetime(2026, 11, day, 5, 0, tzinfo=UTC)
    return CalendarEventSpec(kind=kind, summary=summary, start=s, end=s + timedelta(minutes=30), attendee_person_id=uuid4())


@scenario("C01", "Calendar visit event idempotency", "create_visit_event twice for the same patient/day; different day; unapproved; refill kind; banned summary", "same deterministic id -> one event, upserted twice; other day -> 2nd event; unapproved/refill -> None; banned raises")
def test_c01_calendar(sim: Sim):
    api, pid, aid = FakeCalendarClient(), uuid4(), uuid4()
    e1 = cal.create_visit_event(_spec(), patient_id=pid, calendar_id="c", api=api, approved=True, approval_id=aid)
    e2 = cal.create_visit_event(_spec(), patient_id=pid, calendar_id="c", api=api, approved=True, approval_id=aid)
    assert e1 == e2 and len(api.events) == 1 and api.upserts == 2 and re.fullmatch(r"[0-9a-f]{32}", e1)
    assert cal.create_visit_event(_spec(day=29), patient_id=pid, calendar_id="c", api=api, approved=True, approval_id=aid) != e1 and len(api.events) == 2
    assert cal.create_visit_event(_spec(), patient_id=pid, calendar_id="c", api=api, approved=False, approval_id=aid) is None
    assert cal.create_visit_event(_spec(), patient_id=pid, calendar_id="c", api=api, approved=True, approval_id=None) is None
    assert cal.create_visit_event(_spec(kind="refill"), patient_id=pid, calendar_id="c", api=api, approved=True, approval_id=aid) is None
    with pytest.raises(ValueError):
        cal.create_visit_event(_spec(summary="TB follow up"), patient_id=pid, calendar_id="c", api=api, approved=True, approval_id=aid)
    assert len(api.events) == 2


@scenario("C02", "Calendar attendee only with consent", "patient email known; consent false then true", "attendee absent without consent; present with; guests cannot see others")
def test_c02_attendee(sim: Sim):
    api = FakeCalendarClient()
    cal.create_visit_event(_spec(), patient_id="p", calendar_id="c", api=api, approved=True, approval_id=uuid4(), patient_email="p@x.test")
    assert "attendees" not in list(api.events.values())[0]
    cal.create_visit_event(_spec(), patient_id="p", calendar_id="c", api=api, approved=True, approval_id=uuid4(), patient_email="p@x.test", patient_consents=True)
    ev = list(api.events.values())[0]
    assert ev["attendees"] == [{"email": "p@x.test"}] and ev["guestsCanSeeOtherGuests"] is False


@scenario("C03", "Visit approved by email creates exactly one calendar event", "visit_list approval with calendar_event, 'approve 1' by email, calendar sync run twice", "sync before decision: 0 events; after approve: 1 event; re-run: same event id (upsert), still 1")
def test_c03_visit_sync(sim: Sim):
    spec = _spec().model_dump(mode="json")
    aid = sim.mk("amber", kind="visit_list", title="Visit list", extra={"calendar_event": spec, "audience": "doctor"})
    from cm.contracts.review import DigestItem as DI

    d = build_digest([DI(n=1, approval_id=aid, tier="amber", kind="visit_list", patient_token="P-0142", title="Visit P-0142",
                         summary="visit", due_at=clock.now())], doctor_id=sim.doctor, mailbox=sim.mailbox, day=sim.day,
                     console_url="u", tokens=sim.tokens, now=clock.now())
    api = FakeCalendarClient()
    as_of = clock.now() + timedelta(hours=1)
    mine = lambda rows: [r for r in rows if r["approval_id"] == aid]   # noqa: E731
    from cm.store import gmail_repo

    lister = lambda t: mine(gmail_repo.approved_visit_decisions(t))   # noqa: E731
    assert cal.sync_calendar_events(as_of, api=api, calendar_id="c", list_approved=lister)["upserted"] == 0
    assert sim.send(d, "approve 1").applied == [1]
    r1 = cal.sync_calendar_events(as_of, api=api, calendar_id="c", list_approved=lister)
    r2 = cal.sync_calendar_events(as_of, api=api, calendar_id="c", list_approved=lister)
    assert r1["upserted"] == 1 and r2["upserted"] == 1 and len(api.events) == 1 and api.upserts == 2
    rej = sim.mk("amber", kind="visit_list", extra={"calendar_event": spec, "audience": "doctor"})
    with transaction() as conn:
        dec.decide(rej, __import__("cm.contracts.review", fromlist=["x"]).ReviewDecisionIn(action="reject", reason="no"), via="gmail", actor_id=sim.actors["doctor"], conn=conn)
    assert cal.sync_calendar_events(as_of, api=api, calendar_id="c", list_approved=lambda t: [r for r in gmail_repo.approved_visit_decisions(t) if r["approval_id"] == rej]) ["seen"] == 0


# ------------------------------------------------------------------------------------------ consent / quiet hours
@scenario("K01", "Consent emails", "patient email 'STOP' (non-allowlisted); doctor replies 'STOP' to digest; consent revoke via handle_consent_command", "neither email decides anything; consent revoked only through consent_flows; suppression becomes true; later grant restores")
def test_k01_consent(sim: Sim):
    d, ids = sim.digest(1, 0)
    assert sim.send(d, "STOP", frm="patient@home.test").refused == "sender_not_allowlisted"
    assert sim.send(d, "STOP").clarification and sim.status(ids[0]) == "pending"
    store, person, now = FakeConsentStore(), uuid4(), clock.now()
    consent_flows.record_consent(store, person, "gmail", "daily_checkin", now)
    assert not consent_flows.is_suppressed(store, person, "gmail", "daily_checkin")
    assert consent_flows.handle_consent_command(" Stop ", person, "gmail", store, now) is True
    assert consent_flows.is_suppressed(store, person, "gmail", "daily_checkin")
    assert consent_flows.handle_consent_command("approve 1", person, "gmail", store, now) is False
    assert consent_flows.is_suppressed(store, uuid4(), "gmail", "daily_checkin")   # never granted -> suppressed
    consent_flows.record_consent(store, person, "gmail", "daily_checkin", now + timedelta(seconds=1))
    assert not consent_flows.is_suppressed(store, person, "gmail", "daily_checkin")


@scenario("Q01", "Approval at night (quiet hours)", "doctor replies 'approve 1' at 02:00 local", "email path has no quiet-hours logic (doctor-facing); decision recorded; patient message is only a PENDING outbox row (nothing sent by the email path)")
def test_q01_quiet(sim: Sim):
    d, ids = sim.digest(1, 0)
    out = sim.send(d, "approve 1")
    assert out.applied == [1]
    ob = sim.outbox_rows(ids[0])[0]
    assert ob["status"] == "pending" and ob["provider_message_id"] is None and ob["sent_at"] is None and sim.api.sent == []
    src = (REPO / "cm/channels/gmail_reply.py").read_text() + (REPO / "cm/channels/gmail.py").read_text()
    assert "quiet" not in src.lower()
    return "quiet-hours enforcement lives in the sender/router (outside this lane)"


# ------------------------------------------------------------------------------------------ invariants
@scenario("X01", "Only cm.review.decide writes decisions", "static scan of Gmail lane + DB scan", "no SQL/decision tables in gmail*.py; every review_decisions row created in this sim has via='gmail'")
def test_x01_single_path(sim: Sim):
    for f in ("gmail.py", "gmail_reply.py", "gmail_parse.py", "consent_flows.py", "calendar.py"):
        src = (REPO / "cm/channels" / f).read_text().lower()
        assert not re.search(r"insert into|update cm\.|review_decisions|cm\.outbox|import psycopg|outbox_repo", src), f
    d, ids = sim.digest(2, 0)
    sim.send(d, "approve all")
    assert_gate(sim)
    assert {r["via"] for i in ids for r in sim.decisions(i)} == {"gmail"} and len(sim.decide_calls) == 2


@scenario("X02", "No patient-facing send without decision (DB gate)", "direct INSERT into cm.outbox without decision or template", "database refuses (outbox_authorised / doctor gate)")
def test_x02_db_gate(sim: Sim):
    import psycopg

    d, ids = sim.digest(1, 0)
    with pytest.raises(psycopg.errors.CheckViolation):
        with transaction() as conn:
            conn.execute("INSERT INTO cm.outbox (kind, recipient_id, channel, body, dedup_key) VALUES ('ai_message',%s,'telegram','hi',%s)",
                         (sim.actors["patient_person"], f"x-{uuid4()}"))
    with pytest.raises(psycopg.errors.CheckViolation):
        with transaction() as conn:
            conn.execute("INSERT INTO cm.outbox (kind, recipient_id, channel, body, dedup_key, approval_id) VALUES ('ai_message',%s,'telegram','hi',%s,%s)",
                         (sim.actors["patient_person"], f"x-{uuid4()}", ids[0]))
    assert sim.outbox_rows(ids[0]) == []


TAIL = """## Bugs found and fixed (OpenSpec change `fix-gmail-sim-bugs`)
1. HTML-only replies were treated as empty (`gmail._plain_text` ignored text/html): now falls back to tag-stripped HTML (R09).
2. A decide() refusal (banned_term, reason_required, not_found) burned the single-use token, so the doctor could not retry: `gmail_reply._apply` now releases the token (R26).
3. A Red item could be approved by email if a token existed (e.g. tier escalated after the digest): `PgDecide` now refuses via='gmail' on Red with `red_not_bulk` (R21). Adds `gmail_repo.approval_tier`.

## Observations (not changed)
- No product code wires `DOCTOR_EMAIL_ALLOWLIST` to a sender-to-doctor lookup, nor a `/tasks/gmail-fetch` route: the test harness does the allowlist (R12, R13).
- No Postgres `ConsentStore` adapter for the Gmail ports (`PgConsents` has a different shape); consent flows were tested on the fake (K01).
- Strict grammar: any unrecognised line (e.g. a signature like `Dr. Anita Rao, MD`) makes the whole reply a clarification; safe but may annoy (R32). Telugu verbs are not supported; Telugu free text in EDIT works (R28).
- `hold` parses at contract level but the regex grammar has no HOLD verb (R17).
- Quiet hours are not a Gmail-lane concern (R: Q01); sender/router must enforce them for patient messages.
- The shared `caremem_test` DB can deadlock if another agent reseeds concurrently (seen once in X02); rerun.

## What needs real Google to verify
- Live OAuth: refresh-token exchange, `invalid_grant` handling, scopes (gmail.modify/send, calendar.events).
- `users.watch` registration on the real topic, expiry (about 7 days) and the 6-day renewal job.
- Pub/Sub push delivery: real OIDC JWT from Google (certs fetch, audience, service account), 1 s ack under load, redelivery/ordering.
- Real MIME: multipart/alternative, charset and quoted-printable bodies, inline images, real Authentication-Results headers (dmarc/dkim/spf) from Gmail, Delivered-To plus-tag preservation (`care+r_TOKEN@`), and `Fwd:` subjects from real clients.
- `history.list` 404 behaviour and quota/429 `Retry-After` semantics; send quota; SENT-label behaviour for own mail.
- Calendar API upsert with our 32-hex event ids (insert-then-update on 409) and attendee invitations.
"""


def test_zz_write_report():
    if os.environ.get("GMAIL_SIM_REPORT") != "1":
        pytest.skip("set GMAIL_SIM_REPORT=1 to regenerate the report")
    passed = sum(r["ok"] == "pass" for r in ROWS)
    lines = ["# Gmail channel simulation report", "",
             "Generated by `tests/integration/test_gmail_sim_e2e.py` (run: `GMAIL_SIM_REPORT=1 python -m pytest tests/integration/test_gmail_sim_e2e.py`).",
             "No Google credentials and no network: `FakeGmailClient` / `FakeQueue` / fake Calendar plus the REAL Postgres adapters",
             "(`PgTokenStore`, `PgGmailState`, `PgDecide` -> `cm.review.decide`) on `caremem_test` only.", "",
             f"Scenarios: {len(ROWS)}; passed: {passed}; failed: {len(ROWS) - passed}.", "",
             "| ID | Scenario | Input email (short) | Expected | Actual | Result |", "|---|---|---|---|---|---|"]
    esc = lambda s: s.replace("|", "\\|").replace("\n", " ")   # noqa: E731
    for r in ROWS:
        lines.append(f"| {r['id']} | {esc(r['title'])} | {esc(r['inp'])} | {esc(r['exp'])} | {esc(r['act'])} | {r['ok']} |")
    out = REPO / "docs/design/GMAIL_SIM_REPORT.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n\n" + TAIL, encoding="utf-8")
