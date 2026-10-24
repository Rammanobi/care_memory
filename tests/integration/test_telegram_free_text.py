"""Free text from the Telegram chat: stored, routed to the doctor, one template ack. Test DB + fakes only."""

import itertools
import time
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest

from cm.channels import tg_text
from cm.channels.tg_client import FakeTelegramClient
from cm.contracts.review import ReviewDecisionIn
from cm.core import clock
from cm.core.db import transaction
from cm.jobs import outbox_drainer
from cm.review.decide import decide
from cm.router.banned import find_banned
from tests.integration.test_telegram_pg import (  # noqa: F401
    BASE,
    CHAT,
    bind,
    env,
    msg,
    post,
    q,
)

pytestmark = pytest.mark.db
U = uuid4().int % 10**8 * 100  # fresh update ids each run: events are append-only
DAYS = itertools.count(int(time.time() // 60) % 100000 + 400)  # ever later days: audit rows are permanent
ACK_EN = "Your message has been passed to your care team"


def reqs(env: dict[str, Any]) -> list[dict[str, Any]]:
    return q(
        "SELECT * FROM cm.approvals WHERE patient_id=%s AND thread_id LIKE 'req-tg-%%' ORDER BY created_at, thread_id",
        env["patient"],
    )


@pytest.fixture()
def bound(env: dict[str, Any]) -> dict[str, Any]:
    with transaction() as conn:
        conn.execute("DELETE FROM cm.approvals WHERE patient_id=%s AND (thread_id LIKE 'req-tg-%%' OR thread_id LIKE 'fast-%%')", (env["patient"],))
    # audit_log is append-only: a unique day per test keeps the ack window clean
    clock.pin(BASE + timedelta(days=next(DAYS)))
    bind(env)
    return env


def test_normal_text_creates_request_event_and_one_ack(bound: dict[str, Any]) -> None:
    st, body = post(bound, msg("Can you tell the clinic I am travelling on Friday", U + 1))
    assert st == 200 and body["method"] == "sendMessage" and ACK_EN in body["text"]
    assert not find_banned(body["text"]) and "Friday" not in body["text"]
    r = reqs(bound)
    assert len(r) == 1 and r[0]["tier"] == "green" and r[0]["status"] == "pending"
    d = r[0]["payload"]["data"]
    assert d["source"] == "telegram" and "travelling" in d["text"] and d["priority"] == "normal"
    assert r[0]["payload"]["subkind"] == "patient_request"
    ev = q("SELECT * FROM cm.events WHERE idempotency_key=%s", f"tg:{U + 1}")[0]
    assert ev["type"] == "ContextNote" and ev["consent_id"] is not None


def test_telugu_gets_telugu_ack(bound: dict[str, Any]) -> None:
    with transaction() as conn:
        conn.execute("UPDATE cm.identity_vault SET lang='te' WHERE person_id=%s", (bound["person"],))
    try:
        st, body = post(bound, msg("నేను రేపు రాలేను", U + 2))
        assert "సంరక్షణ బృందానికి" in body["text"] and not find_banned(body["text"])
        assert len(reqs(bound)) == 1
    finally:
        with transaction() as conn:
            conn.execute("UPDATE cm.identity_vault SET lang='en' WHERE person_id=%s", (bound["person"],))


def test_very_long_text_is_clipped_and_emoji_safe(bound: dict[str, Any]) -> None:
    text = "😀 hello " * 1500
    st, body = post(bound, msg(text, U + 3))
    assert ACK_EN in body["text"]
    d = reqs(bound)[0]["payload"]["data"]
    assert len(d["text"]) <= tg_text.MAX_TEXT and d["truncated"] is True and "😀" in d["text"]


def test_duplicate_update_and_rapid_repeats(bound: dict[str, Any]) -> None:
    assert ACK_EN in post(bound, msg("please call me", U + 4))[1]["text"]
    assert post(bound, msg("please call me", U + 4))[1] == {"ok": True}  # same update_id
    assert post(bound, msg("please call me", U + 5))[1] == {"ok": True}  # new id, same words, ack limited
    assert len(reqs(bound)) == 1  # repeat folded into the first request
    assert q("SELECT count(*) AS n FROM cm.events WHERE idempotency_key IN (%s,%s)", f"tg:{U + 4}", f"tg:{U + 5}")[0]["n"] == 2


def test_ack_rate_limit_ten_minutes(bound: dict[str, Any]) -> None:
    assert ACK_EN in post(bound, msg("first question", U + 6))[1]["text"]
    assert post(bound, msg("second different message", U + 7))[1] == {"ok": True}
    assert len(reqs(bound)) == 2  # both reach the doctor, only one ack
    clock.pin(clock.now() + timedelta(minutes=11))
    assert ACK_EN in post(bound, msg("third message later", U + 8))[1]["text"]


def test_danger_text_makes_red_draft_and_urgent_ack(bound: dict[str, Any]) -> None:
    st, body = post(bound, msg("I am coughing blood and feel very weak", U + 9))
    assert "108" in body["text"] and not find_banned(body["text"])
    r = reqs(bound)[0]
    assert r["tier"] == "red" and r["payload"]["data"]["priority"] == "high"
    assert r["due_at"] <= clock.now() + timedelta(hours=1)
    red = q(
        "SELECT tier FROM cm.approvals WHERE patient_id=%s AND thread_id LIKE 'fast-red_symptom-%%'",
        bound["patient"],
    )
    assert len(red) == 1 and red[0]["tier"] == "red"
    assert tg_text.classify("రక్తం వాంతి అవుతోంది") == "danger"
    post(bound, msg("రక్తం వాంతి అవుతోంది", U + 10))
    assert len(reqs(bound)) == 2 and reqs(bound)[1]["tier"] == "red"


def test_advice_request_goes_to_doctor_amber_never_answered(bound: dict[str, Any]) -> None:
    for t in ("should I stop the tablets?", "can I skip my medicine tomorrow", "నేను మాత్రలు ఆపాలా?"):
        assert tg_text.classify(t) == "advice", t
    st, body = post(bound, msg("should I stop the tablets?", U + 11))
    assert ACK_EN in body["text"] and "stop" not in body["text"].lower()
    r = reqs(bound)[0]
    assert r["tier"] == "amber" and r["payload"]["data"]["priority"] == "high"


def test_banned_words_in_patient_text_never_echoed(bound: dict[str, Any]) -> None:
    st, body = post(bound, msg("my TB medicine rifampicin is finished call 9876543210", U + 12))
    assert not find_banned(body["text"]) and "9876543210" not in body["text"]
    ev = q("SELECT payload FROM cm.events WHERE idempotency_key=%s", f"tg:{U + 12}")[0]["payload"]
    assert "9876543210" not in ev["text_tokenised"]


def test_unbound_chat_gets_invitation_only(env: dict[str, Any]) -> None:
    with transaction() as conn:
        conn.execute("DELETE FROM cm.approvals WHERE patient_id=%s AND thread_id LIKE 'req-tg-%%'", (env["patient"],))
    st, body = post(env, msg("hello", U + 13))
    assert "by invitation" in body["text"] and not reqs(env)


def test_after_stop_nothing_stored_or_acked(bound: dict[str, Any]) -> None:
    assert "turned off" in post(bound, msg("/stop", U + 14))[1]["text"]
    st, body = post(bound, msg("are you there", U + 15))
    assert ACK_EN not in body.get("text", "")
    assert not reqs(bound) and not q("SELECT 1 FROM cm.events WHERE idempotency_key=%s", f"tg:{U + 15}")


def test_non_text_message_ignored(bound: dict[str, Any]) -> None:
    upd = {
        "update_id": U + 16,
        "message": {"message_id": 1, "chat": {"id": int(CHAT), "type": "private"}, "photo": [{}]},
    }
    assert post(bound, upd)[1] == {"ok": True} and not reqs(bound)


def test_doctor_reply_is_delivered_through_gated_outbox(bound: dict[str, Any]) -> None:
    post(bound, msg("is my next visit on Monday?", U + 17))
    rid = reqs(bound)[0]["approval_id"]
    with transaction() as conn:
        doc = conn.execute("SELECT person_id FROM cm.persons WHERE token='D-01'").fetchone()["person_id"]
    out = decide(
        rid,
        ReviewDecisionIn(action="edit", edited={"body": "Yes, your visit is on Monday at 10 am."}),
        via="console",
        actor_id=doc,
    )
    assert len(out.outbox_ids) == 1
    row = q("SELECT channel, approval_id FROM cm.outbox WHERE outbox_id=%s", out.outbox_ids[0])[0]
    assert row["channel"] == "telegram" and row["approval_id"] == rid
    client = FakeTelegramClient()
    res = outbox_drainer.drain_once(client)
    assert res["sent"] == 1 and client.sent[0]["chat_id"] == CHAT
    assert "Monday at 10 am" in client.sent[0]["text"]


def test_templates_are_clean_and_ack_has_no_advice() -> None:
    for urgent in (False, True):
        for lang in ("en", "te"):
            _, text = tg_text.ack_text(urgent, lang, "TB")  # a banned first name falls back
            assert not find_banned(text)
    assert "friend" in tg_text.ack_text(False, "en", "TB")[1]
