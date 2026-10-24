import base64
import json
from datetime import UTC, datetime, timedelta
from typing import get_args
from uuid import uuid4

import pytest

from cm.channels import gmail as g
from cm.channels.calendar import create_visit_event, event_id
from cm.channels.consent_flows import handle_consent_command, is_suppressed, record_consent
from cm.channels.fakes_gmail import (
    FakeAudit,
    FakeCalendarClient,
    FakeConsentStore,
    FakeDecide,
    FakeGmailClient,
    FakeOutboxWriter,
    FakeQueue,
    FakeState,
    FakeTokens,
)
from cm.channels.gmail_parse import parse_reply, strip_quoted
from cm.channels.gmail_reply import handle_reply
from cm.channels.ports_gmail import GmailAuthError, GmailQuotaError, has_banned_term
from cm.contracts.api import CalendarEventSpec, PubSubPush
from cm.contracts.review import DigestItem, ReviewKind
from cm.router.degrade import degrade_order, next_channel

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
BOX, DOC, DOCID = "clinic@example.org", "doc@example.org", "d1"
T = "tok" + "A" * 13
GOOD_AUTH = "mx; dmarc=pass; dkim=pass; spf=pass"


def push(email=BOX, hid=500):
    data = base64.b64encode(json.dumps({"emailAddress": email, "historyId": hid}).encode()).decode()
    return PubSubPush.model_validate({"message": {"data": data, "messageId": "m1"}})


def reply_msg(text, mid="r1", sender=DOC, auth=GOOD_AUTH, subject="Re: CareMemory review", extra=None):
    h = {"from": sender, "subject": subject, "authentication-results": auth,
         "delivered-to": f"clinic+r_{T}@example.org", "in-reply-to": f"<digest-{DOCID}-2026-10-24@caremem>",
         "message-id": "<x@y>"}
    h.update(extra or {})
    return {"id": mid, "thread_id": "th1", "labels": ["INBOX"], "headers": h, "text": text}


def setup(n=3, ttl=timedelta(hours=48)):
    tokens, ids = FakeTokens(), {}
    for i in range(1, n + 1):
        ids[i] = uuid4()
        tokens.mint([(g.token_hash(T, i), ids[i])], DOCID, NOW + ttl)
    return tokens, ids, FakeDecide(), FakeOutboxWriter(), FakeAudit()


def run(msg, tokens, decide, outbox, audit, now=NOW):
    return handle_reply(msg, doctor_id=DOCID, doctor_email=DOC, tokens=tokens, decide=decide, now=now,
                        outbox=outbox, audit=audit)


# ---- parser
@pytest.mark.parametrize("text,verb,items,txt", [
    ("approve 1 and 2", "approve", [1, 2], None),
    ("APPROVE 1-3", "approve", [1, 2, 3], None),
    ("Approve all", "approve", [], None),
    ("reject 3", "reject", [3], None),
    ("reject 3: not due yet", "reject", [3], "not due yet"),
    ("edit 2: Visit Wednesday evening", "edit", [2], "Visit Wednesday evening"),
])
def test_grammar(text, verb, items, txt):
    p = parse_reply(text)
    assert not p.needs_clarification
    c = p.parse.commands[0]
    assert (c.verb, c.items, c.text) == (verb, items, txt)


@pytest.mark.parametrize("text", ["please do whatever you think", "edit 2", "approve 99", "approve", "delete 1",
                                  "approve 1\nmaybe later"])
def test_unknown_never_acts(text):
    assert parse_reply(text).needs_clarification


def test_quoted_history_stripped():
    body = "approve 1\n\nOn Mon, 5 Oct, Clinic <c@x> wrote:\n> approve 2\n> reject 3"
    assert parse_reply(body).parse.commands[0].items == [1]
    assert "reject" not in strip_quoted("ok thanks\n> reject 3")
    assert not parse_reply("> approve 1").parse.commands


# ---- push
def test_push_acks_and_dedupes():
    q = FakeQueue()
    assert g.handle_push(push(), q, BOX) == 204
    assert g.handle_push(push(), q, BOX) == 204
    assert list(q.tasks) == ["gmail-fetch-500"]


def test_push_garbage_and_foreign_mailbox_acked_not_queued():
    q = FakeQueue()
    bad = PubSubPush.model_validate({"message": {"data": "!!notbase64"}})
    assert g.handle_push(bad, q, BOX) == 204 and g.handle_push(push("other@x.org"), q, BOX) == 204
    assert not q.tasks


# ---- fetch
def mail(mid, sender="someone@x.org", labels=("INBOX",)):
    return {"id": mid, "thread_id": "t", "labels": list(labels), "headers": {"from": sender}, "text": ""}


def test_fetch_skips_own_and_is_idempotent():
    api, st, seen = FakeGmailClient(), FakeState(), []
    st.cursor = 100
    api.add_inbound(mail("a"))
    api.add_inbound(mail("b", sender=BOX, labels=("SENT",)))
    r = g.fetch_worker(101, api=api, state=st, mailbox=BOX, on_message=seen.append)
    assert [m["id"] for m in seen] == ["a"] and r.skipped_own == ["b"] and st.cursor == 102
    st.cursor = 100  # redelivered task with stale cursor
    r2 = g.fetch_worker(101, api=api, state=st, mailbox=BOX, on_message=seen.append)
    assert len(seen) == 1 and sorted(r2.skipped_dup) == ["a", "b"] and api.get_count == 2


def test_cursor_loss_falls_back_to_recent():
    api, st, seen = FakeGmailClient(), FakeState(), []
    st.cursor, api.cursor_floor = 5, 50
    api.add_inbound(mail("a"))
    r = g.fetch_worker(101, api=api, state=st, mailbox=BOX, on_message=seen.append)
    assert r.cursor_reset and len(seen) == 1 and st.cursor == api.latest


def test_quota_error_retried_honouring_retry_after_then_ok():
    api, st, sleeps = FakeGmailClient(), FakeState(), []
    st.cursor = 100
    api.errors = [GmailQuotaError(7.0)]
    g.fetch_worker(100, api=api, state=st, mailbox=BOX, on_message=lambda m: None, sleep=sleeps.append)
    assert sleeps == [7.0] and api.calls.count("history_list") == 2


def test_quota_exhausted_keeps_cursor_and_auth_not_retried():
    api, st = FakeGmailClient(), FakeState()
    st.cursor = 100
    api.errors = [GmailQuotaError(1)] * 10
    with pytest.raises(GmailQuotaError):
        g.fetch_worker(100, api=api, state=st, mailbox=BOX, on_message=lambda m: None, sleep=lambda s: None)
    assert st.cursor == 100
    api2 = FakeGmailClient()
    api2.errors = [GmailAuthError()]
    with pytest.raises(GmailAuthError):
        g.fetch_worker(100, api=api2, state=st, mailbox=BOX, on_message=lambda m: None, sleep=lambda s: None)
    assert api2.calls == ["history_list"]


# ---- reply verification
def test_approve_edit_reject_apply_via_decide():
    tokens, ids, decide, outbox, audit = setup()
    out = run(reply_msg("approve 1\nedit 2: Visit Wednesday evening\nreject 3: no"), tokens, decide, outbox, audit)
    assert out.applied == [1, 3] and out.edited == [2]
    assert [c[2] for c in decide.calls] == ["gmail"] * 3
    assert decide.calls[1][1].edited == {"body": "Visit Wednesday evening"}
    assert decide.calls[2][1].reason == "no"
    assert "echo:r1" in outbox.rows


def test_token_one_time_use():
    tokens, ids, decide, outbox, audit = setup()
    run(reply_msg("approve 1"), tokens, decide, outbox, audit)
    out = run(reply_msg("approve 1", mid="r2"), tokens, decide, outbox, audit)
    assert len(decide.calls) == 1 and out.skipped[1] == "already applied"


def test_expired_token_refused():
    tokens, ids, decide, outbox, audit = setup(ttl=timedelta(hours=1))
    out = run(reply_msg("approve 1"), tokens, decide, outbox, audit, now=NOW + timedelta(hours=2))
    assert not decide.calls and out.skipped[1] == "link expired"


def test_approve_all_stops_at_missing_token():
    tokens, ids, decide, outbox, audit = setup(n=3)
    out = run(reply_msg("approve all"), tokens, decide, outbox, audit)
    assert out.applied == [1, 2, 3]


@pytest.mark.parametrize("kw", [
    dict(sender="evil@x.org"),
    dict(auth="mx; dmarc=fail; spf=pass"),
    dict(subject="Fwd: CareMemory review"),
    dict(extra={"in-reply-to": "<random@x>"}),
    dict(extra={"delivered-to": "clinic@example.org", "to": "clinic@example.org"}),
    dict(extra={"sender": "attacker@x.org"}),
])
def test_spoofed_forwarded_or_wrong_thread_refused(kw):
    tokens, ids, decide, outbox, audit = setup()
    out = run(reply_msg("approve 1", **kw), tokens, decide, outbox, audit)
    assert out.refused and not decide.calls and audit.events and not outbox.rows
    assert tokens.rows[g.token_hash(T, 1)]["used"] is False


def test_unknown_text_clarifies_and_consumes_nothing():
    tokens, ids, decide, outbox, audit = setup()
    out = run(reply_msg("sure go ahead with everything"), tokens, decide, outbox, audit)
    assert out.clarification and not decide.calls and "echo:r1" in outbox.rows
    assert not tokens.rows[g.token_hash(T, 1)]["used"]


def test_console_already_decided_is_skipped_and_decide_failure_releases_token():
    tokens, ids, decide, outbox, audit = setup()
    decide.already.add(ids[1])
    out = run(reply_msg("approve 1"), tokens, decide, outbox, audit)
    assert out.skipped[1] == "already decided in console"

    def boom(*a, **k):
        raise RuntimeError("db down")

    out = run(reply_msg("approve 2", mid="r9"), tokens, boom, outbox, audit)
    assert 2 in out.skipped and not tokens.rows[g.token_hash(T, 2)]["used"]


# ---- digest and outbound
def items():
    kind = get_args(ReviewKind)[0]
    return [DigestItem(n=i, approval_id=uuid4(), tier="amber", kind=kind, title=f"Item {i}",
                       summary="Visit due soon", due_at=NOW) for i in (1, 2)]


def test_digest_content_tokens_and_red_unnumbered():
    tokens = FakeTokens()
    d = g.build_digest(items(), doctor_id=DOCID, mailbox=BOX, day="2026-10-24", console_url="https://c",
                       red_titles=["Urgent patient P7"], tokens=tokens, now=NOW, token=T)
    assert d.body_text.index("APPROVE 1-5") < d.body_text.index("1. [AMBER]")
    assert "Console only" in d.body_text and "Urgent patient P7" in d.body_text
    assert "3." not in d.body_text and "<ol>" in d.body_html and d.reply_to == f"clinic+r_{T}@example.org"
    assert d.message_id == "<digest-d1-2026-10-24@caremem>" and d.subject.endswith(T[:6])
    assert set(tokens.rows) == {g.token_hash(T, 1), g.token_hash(T, 2)}
    assert not has_banned_term(d.body_text + d.body_html)
    assert g.build_digest([], doctor_id=DOCID, mailbox=BOX, day="x", console_url="") is None


def row(**kw):
    base = dict(outbox_id=uuid4(), to=DOC, subject="s", body_text="b", approval_ref=uuid4())
    base.update(kw)
    return g.OutboxRow(**base)


def test_send_refuses_without_approval_ref():
    api = FakeGmailClient()
    r = g.send_outbox_row(row(approval_ref=None), api)
    assert r.status == "skipped" and r.skip_reason == "invalid_approval" and not api.sent


def test_send_ok_quota_retry_and_auth_no_retry():
    api, sleeps = FakeGmailClient(), []
    assert g.send_outbox_row(row(), api, sleep=sleeps.append).status == "sent"
    api.errors = [GmailQuotaError(3.0)]
    assert g.send_outbox_row(row(), api, sleep=sleeps.append).status == "sent" and sleeps == [3.0]
    api.errors = [GmailQuotaError(2.0)] * 10
    r = g.send_outbox_row(row(), api, sleep=lambda s: None, tries=2)
    assert r.status == "retry" and r.retry_after_s == 2.0
    api.errors, api.calls = [GmailAuthError()], []
    assert g.send_outbox_row(row(), api).status == "failed" and api.calls == ["send"]


def test_send_already_sent_and_banned():
    api = FakeGmailClient()
    assert g.send_outbox_row(row(provider_message_id="x"), api).skip_reason == "already_sent"
    assert g.send_outbox_row(row(body_text="rifampicin dose"), api, check_banned=True).skip_reason == "banned_term"


# ---- watch
def test_watch_renewal_pure_and_job():
    ms = int((NOW + timedelta(days=7)).timestamp() * 1000)
    assert g.should_renew_watch(None, None, NOW)
    assert not g.should_renew_watch(ms, NOW - timedelta(days=2), NOW)
    assert g.should_renew_watch(ms, NOW - timedelta(days=6), NOW)
    assert g.should_renew_watch(int((NOW + timedelta(hours=10)).timestamp() * 1000), NOW, NOW)
    api, st = FakeGmailClient(), FakeState()
    assert g.renew_watch_job(api=api, state=st, topic="t", now=NOW, last_renewed=None) and st.expiry


# ---- calendar
def spec(**kw):
    base = dict(kind="visit", summary="Clinic visit", start=NOW, end=NOW + timedelta(minutes=30), attendee_person_id=uuid4())
    base.update(kw)
    return CalendarEventSpec(**base)


def test_calendar_idempotent_no_attendee_leak_and_needs_approval():
    cal, pid = FakeCalendarClient(), uuid4()
    s = spec()
    kw = dict(patient_id=pid, calendar_id="primary", api=cal, patient_email="p@x.org", approval_id=uuid4())
    a = create_visit_event(s, approved=True, **kw)
    b = create_visit_event(s, approved=True, **kw)
    assert a == b == event_id("visit", pid, NOW.date().isoformat()) and len(cal.events) == 1
    assert "attendees" not in cal.events[a]
    create_visit_event(s, approved=True, patient_consents=True, **kw)
    assert cal.events[a]["attendees"] == [{"email": "p@x.org"}]
    assert create_visit_event(s, approved=False, **kw) is None
    assert create_visit_event(s, approved=True, **{**kw, "approval_id": None}) is None
    with pytest.raises(ValueError):
        create_visit_event(spec(summary="TB clinic"), approved=True, **kw)


# ---- consent and degrade
def test_consent_record_revoke_suppress():
    st, p = FakeConsentStore(), uuid4()
    assert is_suppressed(st, p, "gmail", "care_coordination")
    record_consent(st, p, "gmail", "care_coordination", NOW)
    assert not is_suppressed(st, p, "gmail", "care_coordination")
    assert handle_consent_command("STOP", p, "gmail", st, NOW)
    assert is_suppressed(st, p, "gmail", "care_coordination")
    assert not handle_consent_command("hello", p, "gmail", st, NOW)


def test_degrade_order():
    assert degrade_order() == ["telegram", "gmail", "web_inbox"]
    assert degrade_order(down=["telegram"]) == ["gmail", "web_inbox"]
    assert degrade_order(over_quota=["gmail"], down=["telegram"]) == ["web_inbox"]
    assert degrade_order(consented=["telegram", "gmail"]) == ["telegram", "gmail"]
    assert next_channel(["telegram"], down=[]) == "gmail"
    assert next_channel(["telegram", "gmail", "web_inbox"]) is None
