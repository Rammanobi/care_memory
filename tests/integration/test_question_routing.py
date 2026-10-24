"""Patient question -> research -> doctor notified -> doctor reply threaded on the same channel.

Offline: fake research agent, fake Telegram client, fake doctor_notify. Test database only.
"""

import itertools
import json
import sys
import time
from datetime import timedelta
from types import ModuleType, SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from cm.api.suppress import find_banned
from cm.channels import question_routing as qr
from cm.channels.tg_client import FakeTelegramClient
from cm.contracts.review import ReviewDecisionIn
from cm.core import clock, tasks
from cm.core.config import load_settings
from cm.core.db import transaction
from cm.jobs import outbox_drainer
from cm.review.decide import decide
from cm.store import approvals_repo, outbox_repo
from tests.integration.test_e2e_api import _as
from tests.integration import test_telegram_pg as tgpg
from tests.integration.test_telegram_pg import BASE, CHAT, bind, env, post, q  # noqa: F401

pytestmark = pytest.mark.db
U = uuid4().int % 10**8 * 100 + 50  # fresh update ids each run
DAYS = itertools.count(int(time.time() // 60) % 100000 + 900)  # unique day per test (ack audit rows)
MID = 4242
NL = chr(10)
READY = {
    "status": "ready",
    "category": "medicine_question",
    "priority": "normal",
    "brief": [{"text": "Two doses missed this week", "refs": ["E-0412"]}],
    "suggested_reply": "Please keep taking your medicine and come to the clinic.",
    "confidence": 0.8,
    "model": "fake",
    "cost_usd": 0.0,
    "reason": "",
}


def tmsg(text: str, uid: int, mid: int = MID) -> dict[str, Any]:
    return {
        "update_id": uid,
        "message": {"message_id": mid, "chat": {"id": int(CHAT), "type": "private"}, "text": text},
    }


def reqs(e: dict[str, Any]) -> list[dict[str, Any]]:
    return q(
        "SELECT * FROM cm.approvals WHERE patient_id=%s AND thread_id LIKE 'req-tg-%%' AND created_at >= %s "
        "ORDER BY created_at, thread_id",
        e["patient"],
        clock.now() - timedelta(hours=1),
    )


def doctor() -> UUID:
    return q("SELECT person_id FROM cm.persons WHERE token='D-01'")[0]["person_id"]


def data_of(aid: UUID) -> dict[str, Any]:
    return q("SELECT payload FROM cm.approvals WHERE approval_id=%s", aid)[0]["payload"]["data"]


@pytest.fixture(autouse=True)
def own_patient(monkeypatch: pytest.MonkeyPatch) -> None:
    """Decisions are permanent, so this file uses its own throwaway patient (P-9902), not the shared P-9901."""
    monkeypatch.setattr(tgpg, "TOKEN", "P-9902")


@pytest.fixture()
def bound(env: dict[str, Any]) -> dict[str, Any]:
    with transaction() as conn:
        conn.execute(  # decided rows are permanent (review_decisions is append-only): reqs() filters by day
            "DELETE FROM cm.approvals a WHERE patient_id=%s AND (thread_id LIKE 'req-tg-%%' OR thread_id LIKE 'fast-%%') "
            "AND NOT EXISTS (SELECT 1 FROM cm.review_decisions d WHERE d.approval_id=a.approval_id)",
            (env["patient"],),
        )
    with transaction() as conn:  # other test files leave pending rows; drain_once claims the oldest rows globally
        conn.execute("UPDATE cm.outbox SET status='failed' WHERE status='pending'")
    clock.pin(BASE + timedelta(days=next(DAYS)))
    bind(env)
    return env


@pytest.fixture()
def spy(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Fake research agent, fake doctor_notify, captured SSE publishes."""
    s = SimpleNamespace(notified=[], events=[], priority="normal", research_calls=[])

    def research_question(token: str, question: str, **kw: Any) -> Any:
        s.research_calls.append((token, kw))
        return SimpleNamespace(as_dict=lambda: {**READY, "priority": s.priority})

    agent = SimpleNamespace(
        triage=lambda text: SimpleNamespace(category="medicine_question", priority=s.priority),
        research_question=research_question,
    )
    monkeypatch.setattr(qr, "_load", lambda: agent)
    mod = ModuleType("cm.channels.doctor_notify")
    mod.notify_doctor_new_question = lambda aid, **kw: s.notified.append((aid, kw)) or {"ok": True}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "cm.channels.doctor_notify", mod)
    monkeypatch.setattr(qr.stream_repo, "publish", lambda topic, ev, **k: s.events.append((topic, ev)))
    tasks.reset_for_tests()
    return s


def test_telegram_question_origin_pending_then_researched(bound: dict[str, Any], spy: SimpleNamespace) -> None:
    post(bound, tmsg("Can I skip the evening tablets tomorrow?", U + 1))
    r = reqs(bound)[0]
    d = r["payload"]["data"]
    assert d["origin"] == {
        "channel": "telegram",
        "telegram_chat_id": int(CHAT),
        "telegram_message_id": MID,
        "question_excerpt": "Can I skip the evening tablets tomorrow?",
    }
    assert d["research"]["status"] == "pending" and set(d["research"]) == set(READY)
    assert tasks.run_pending() >= 1  # ingest_event + question_research
    d = data_of(r["approval_id"])
    assert d["research"]["status"] == "ready" and d["research"]["brief"][0]["refs"] == ["E-0412"]
    assert d["doctor_notified"] is True
    assert spy.research_calls[0][1]["model"] == "fake" and spy.research_calls[0][1]["embed"] is False
    aid = str(r["approval_id"])
    assert spy.events == [
        (
            "review",
            {
                "type": "patient_question",
                "kind": "patient_question",
                "ref": aid,
                "approval_id": aid,
                "patient_code": "PT-9902",
                "category": "medicine_question",
                "priority": "normal",
            },
        )
    ]
    assert len(spy.notified) == 1 and spy.notified[0][1]["patient_code"] == "PT-9902"
    assert spy.notified[0][1]["question_excerpt"].startswith("Can I skip")


def test_task_is_idempotent_and_enqueue_dedupes(bound: dict[str, Any], spy: SimpleNamespace) -> None:
    post(bound, tmsg("Is the clinic open on Sunday?", U + 2))
    aid = reqs(bound)[0]["approval_id"]
    qr.enqueue_research(aid)
    qr.enqueue_research(aid)
    tasks.run_pending()
    assert qr.run_question_research(aid)["status"] == "duplicate"
    assert len(spy.events) == 1 and len(spy.notified) == 1 and len(spy.research_calls) == 1


def test_urgent_raises_tier_never_lowers_red(bound: dict[str, Any], spy: SimpleNamespace) -> None:
    spy.priority = "urgent"
    post(bound, tmsg("Is the clinic open on Sunday?", U + 3))
    aid = reqs(bound)[0]["approval_id"]
    assert reqs(bound)[0]["tier"] == "green"
    tasks.run_pending()
    row = q("SELECT tier FROM cm.approvals WHERE approval_id=%s", aid)[0]
    assert row["tier"] == "red" and data_of(aid)["priority"] == "urgent"
    # a Red item stays Red even when the brief says normal
    spy.priority = "normal"
    post(bound, tmsg("I am coughing blood and feel very weak", U + 4, mid=77))
    red = [r for r in reqs(bound) if r["approval_id"] != aid][0]
    assert red["tier"] == "red"
    tasks.run_pending()
    assert q("SELECT tier FROM cm.approvals WHERE approval_id=%s", red["approval_id"])[0]["tier"] == "red"


def _sent_today_row(e: dict[str, Any]) -> None:
    at = clock.now()
    with transaction() as conn:
        aid = uuid4()
        approvals_repo.upsert(
            {
                "approval_id": aid,
                "patient_id": e["patient"],
                "thread_id": f"cap-{aid}",
                "interrupt_id": "x",
                "tier": "green",
                "kind": "needs_human",
                "payload": {"audience": "patient", "title": "t", "body": "b"},
                "created_at": at,
                "due_at": at,
                "expires_at": at + timedelta(days=1),
            },
            conn=conn,
        )
        dec = conn.execute(
            "INSERT INTO cm.review_decisions (approval_id, doctor_id, action, via, evidence_viewed, decided_at) "
            "VALUES (%s,%s,'approve','console',true,%s) RETURNING decision_id",
            (aid, doctor(), at),
        ).fetchone()["decision_id"]
        oid = outbox_repo.enqueue(
            {
                "kind": "ai_message",
                "recipient_id": e["person"],
                "channel": "telegram",
                "body": "x",
                "approval_id": aid,
                "decision_id": dec,
                "next_attempt_at": at,
                "dedup_key": f"cap-{aid}",
            },
            conn=conn,
        )
        outbox_repo.mark(oid, "sent", sent_at=at, conn=conn)


def test_doctor_reply_is_threaded_with_quote_and_exempt_from_cap(bound: dict[str, Any], spy: SimpleNamespace) -> None:
    post(bound, tmsg("Can I skip the evening tablets tomorrow?", U + 5))
    aid = reqs(bound)[0]["approval_id"]
    tasks.run_pending()
    out = decide(
        aid,
        ReviewDecisionIn(action="edit", edited={"body": "Please do not skip. See you Monday."}),
        via="console",
        actor_id=doctor(),
    )
    row = q("SELECT kind, meta FROM cm.outbox WHERE outbox_id=%s", out.outbox_ids[0])[0]
    assert row["kind"] == "ai_message"
    assert row["meta"]["reply_to"] == {
        "approval_id": str(aid),
        "question_excerpt": "Can I skip the evening tablets tomorrow?",
        "telegram_message_id": MID,
    }
    for _ in range(3):  # the 3-per-day cap is already used up by other messages
        _sent_today_row(bound)
    client = FakeTelegramClient()
    outbox_drainer.drain_once(client, limit=1000)  # other due rows (check-in reminders) must not crowd out ours
    threaded = [m for m in client.sent if m.get("reply_to_message_id") == MID]
    assert len(threaded) == 1
    sent = threaded[0]
    assert sent["chat_id"] == CHAT and sent["reply_to_message_id"] == MID
    assert sent["text"] == (
        'Reply to your question: "Can I skip the evening tablets tomorrow?"' + NL * 2 + "Please do not skip. See you Monday."
    )
    assert not find_banned(sent["text"])


def test_reply_is_not_counted_toward_the_cap(bound: dict[str, Any], spy: SimpleNamespace) -> None:
    post(bound, tmsg("Is the clinic open on Sunday?", U + 6))
    aid = reqs(bound)[0]["approval_id"]
    out = decide(aid, ReviewDecisionIn(action="approve"), via="console", actor_id=doctor())
    outbox_drainer.drain_once(FakeTelegramClient(), limit=1000)
    assert q("SELECT status FROM cm.outbox WHERE outbox_id=%s", out.outbox_ids[0])[0]["status"] == "sent"
    assert outbox_repo.sent_today(bound["person"], clock.ist_date(clock.now())) == 0


def test_quiet_hours_only_urgent_reply_goes_out(bound: dict[str, Any], spy: SimpleNamespace) -> None:
    post(bound, tmsg("Is the clinic open on Sunday?", U + 7))
    calm = reqs(bound)[0]["approval_id"]
    tasks.run_pending()
    spy.priority = "urgent"
    post(bound, tmsg("Please call me about my results", U + 8, mid=78))
    urgent = [r for r in reqs(bound) if r["approval_id"] != calm][0]["approval_id"]
    tasks.run_pending()
    assert q("SELECT tier FROM cm.approvals WHERE approval_id=%s", calm)[0]["tier"] == "green"
    outs = {a: decide(a, ReviewDecisionIn(action="approve", reason="ok"), via="console", actor_id=doctor()) for a in (calm, urgent)}
    clock.pin(clock.now().replace(hour=23, minute=30))
    client = FakeTelegramClient()
    outbox_drainer.drain_once(client, limit=1000)
    status = {a: q("SELECT status FROM cm.outbox WHERE outbox_id=%s", o.outbox_ids[0])[0]["status"] for a, o in outs.items()}
    assert status[urgent] == "sent" and status[calm] == "pending"  # quiet hours hold the calm reply only
    assert [m for m in client.sent if m.get("reply_to_message_id") == 78]


def test_declined_question_is_closed_with_no_reply(bound: dict[str, Any], spy: SimpleNamespace) -> None:
    post(bound, tmsg("Is the clinic open on Sunday?", U + 9))
    aid = reqs(bound)[0]["approval_id"]
    decide(aid, ReviewDecisionIn(action="reject", reason="not for the clinic"), via="console", actor_id=doctor())
    assert q("SELECT count(*) AS n FROM cm.outbox WHERE approval_id=%s", aid)[0]["n"] == 0
    assert outbox_drainer.drain_once(FakeTelegramClient())["sent"] == 0


def test_consent_revoked_before_reply_nothing_sent(bound: dict[str, Any], spy: SimpleNamespace) -> None:
    post(bound, tmsg("Is the clinic open on Sunday?", U + 10))
    aid = reqs(bound)[0]["approval_id"]
    out = decide(aid, ReviewDecisionIn(action="approve"), via="console", actor_id=doctor())
    assert post(bound, tmsg("/stop", U + 11))[0] == 200
    client = FakeTelegramClient()
    res = outbox_drainer.drain_once(client)
    assert res["sent"] == 0 and client.sent == []
    row = q("SELECT status, last_error FROM cm.outbox WHERE outbox_id=%s", out.outbox_ids[0])[0]
    assert row["status"] == "failed" and row["last_error"] == "skipped:no_consent"


def test_banned_term_question_has_clean_excerpt(bound: dict[str, Any], spy: SimpleNamespace) -> None:
    post(bound, tmsg("my TB medicine is finished", U + 12))
    d = reqs(bound)[0]["payload"]["data"]
    assert d["origin"]["question_excerpt"] == "" and "TB" in d["text"]  # the doctor keeps the words
    aid = reqs(bound)[0]["approval_id"]
    decide(
        aid,
        ReviewDecisionIn(action="edit", edited={"body": "Please visit the clinic this week."}),
        via="console",
        actor_id=doctor(),
    )
    client = FakeTelegramClient()
    assert outbox_drainer.drain_once(client)["sent"] == 1
    assert client.sent[0]["text"].startswith("Reply to your question:" + NL * 2)


def test_missing_agent_falls_back_to_pending_stub(bound: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qr, "_load", lambda: None)
    notes: list[Any] = []
    monkeypatch.setattr(qr.stream_repo, "publish", lambda t, e, **k: notes.append(e))
    tasks.reset_for_tests()
    post(bound, tmsg("I am coughing blood and feel very weak", U + 13))
    tasks.run_pending()
    r = reqs(bound)[0]
    d = r["payload"]["data"]
    assert d["research"]["status"] == "pending" and d["research"]["reason"] == "agent_missing"
    assert d["priority"] == "urgent" and r["tier"] == "red" and notes[0]["category"] == "danger"


def test_research_failure_is_stored_not_raised(
    bound: dict[str, Any], spy: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("model down")

    agent = SimpleNamespace(
        triage=lambda t: SimpleNamespace(category="x", priority="normal"), research_question=boom
    )
    monkeypatch.setattr(qr, "_load", lambda: agent)
    post(bound, tmsg("Is the clinic open on Sunday?", U + 14))
    tasks.run_pending()
    d = data_of(reqs(bound)[0]["approval_id"])
    assert d["research"]["status"] == "failed" and d["research"]["reason"] == "RuntimeError"
    assert len(spy.notified) == 1  # the doctor still hears about the question


def test_real_notify_reaches_a_listener(bound: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qr, "_load", lambda: None)
    tasks.reset_for_tests()
    with psycopg.connect(load_settings().dsn, autocommit=True) as listener:
        listener.execute("LISTEN cm_events")
        post(bound, tmsg("Is the clinic open on Sunday?", U + 15))
        tasks.run_pending()
        got = [json.loads(n.payload) for n in listener.notifies(timeout=2, stop_after=20)]
    ev = [g for g in got if g.get("kind") == "patient_question"]
    assert ev and ev[0]["topic"] == "review" and ev[0]["patient_code"] == "PT-9902"
    assert "text" not in ev[0] and ev[0].get("person_id") is None  # doctors only, no patient text


# ---- web portal ---------------------------------------------------------------------------------
def _portal_question(text: str = "When is my next visit?") -> tuple[Any, Any, dict[str, Any]]:
    tasks.reset_for_tests()
    pat, doc = _as("ravi.pt0142"), _as("dr.rao")
    r = pat.post("/portal/requests", json={"text": text, "kind": "Medicine question"})
    assert r.status_code == 201, r.text
    return pat, doc, r.json()


def _mine(pat: Any, rid: str) -> dict[str, Any]:
    return {x["id"]: x for x in pat.get("/portal/requests").json()}[rid]


def test_portal_question_waiting_then_answered_in_inbox(pinned_clock: None, spy: SimpleNamespace) -> None:
    pat, doc, made = _portal_question()
    assert made["question_status"] == "waiting" and made["reply"] is None
    tasks.run_pending()
    rid = made["id"]
    d = data_of(UUID(rid))
    assert d["origin"] == {"channel": "portal", "question_excerpt": "When is my next visit?"}
    assert d["research"]["status"] == "ready" and len(spy.notified) == 1
    assert _mine(pat, rid)["question_status"] == "waiting"
    r = doc.post(f"/requests/{rid}/decision", json={"action": "edit", "edited": {"body": "Your visit is on Monday."}})
    assert r.status_code == 200, r.text
    mine = _mine(pat, rid)
    assert mine["question_status"] == "answered" and mine["reply"] == "Your visit is on Monday."
    assert mine["answered_at"]
    inbox = [m for m in pat.get("/portal/inbox").json() if m["in_reply_to"] and m["in_reply_to"]["approval_id"] == rid]
    assert len(inbox) == 1 and inbox[0]["text"] == "Your visit is on Monday."
    assert inbox[0]["in_reply_to"] == {"approval_id": rid, "question_excerpt": "When is my next visit?"}
    # the doctor side carries research, origin and status
    row = {x["id"]: x for x in doc.get("/requests").json()}[rid]
    assert row["status"] == "approved" and row["research"]["status"] == "ready"
    assert row["origin"]["channel"] == "portal" and row["tier"] == "green"
    det = doc.get(f"/review/{rid}").json()
    assert det["status"] == "edited" and det["proposal"]["data"]["research"]["status"] == "ready"
    assert det["proposal"]["data"]["origin"]["channel"] == "portal"


def test_portal_declined_is_closed_and_nothing_leaks(pinned_clock: None, spy: SimpleNamespace) -> None:
    pat, doc, made = _portal_question("Is the clinic open on Sunday?")
    tasks.run_pending()
    r = doc.post(f"/requests/{made['id']}/decision", json={"action": "reject", "reason": "no reply needed"})
    assert r.status_code == 200, r.text
    mine = _mine(pat, made["id"])
    assert mine["question_status"] == "closed" and mine["reply"] is None
    assert not [
        m for m in pat.get("/portal/inbox").json() if m["in_reply_to"] and m["in_reply_to"]["approval_id"] == made["id"]
    ]


def test_no_research_fields_in_any_portal_response(pinned_clock: None, spy: SimpleNamespace) -> None:
    pat, doc, made = _portal_question("Please call me about my results")
    tasks.run_pending()
    doc.post(f"/requests/{made['id']}/decision", json={"action": "approve"})
    forbidden = (
        "research", "brief", "suggested_reply", "confidence", "cost_usd", "origin", "doctor_notified",
        "telegram_chat_id", "Two doses missed", READY["suggested_reply"],
    )  # fmt: skip
    for path in ("/me", "/today", "/record", "/requests", "/consents", "/documents", "/medicines", "/inbox"):
        body = pat.get(f"/portal{path}").text
        for word in forbidden:
            assert word not in body, (path, word)
        assert find_banned(body) == [], path
    assert set(made) == {"id", "text", "kind", "when", "status", "reply", "question_status", "answered_at"}
