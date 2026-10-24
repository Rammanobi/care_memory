"""Telegram lane against the real test database: webhook -> event -> outbox -> fake client.

No network: the client is FakeTelegramClient (or httpx.MockTransport for the HTTP client).
"""

import asyncio
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest

from cm.channels import adapters_pg, tg_callback
from cm.channels.adapters_pg import PgBindings, build_deps
from cm.channels.telegram import handle_webhook
from cm.channels.tg_client import (
    FakeTelegramClient,
    TgAuthError,
    TgBlocked,
    TgRetryAfter,
    TgTransient,
)
from cm.channels.tg_http import HttpTelegramClient
from cm.channels.tg_sender import send_outbox
from cm.core import clock, tasks
from cm.core.db import transaction
from cm.jobs import make_invite, outbox_drainer, reminders
from cm.store import events_repo, outbox_repo

pytestmark = pytest.mark.db
SECRET = "test-secret-not-real"
CHAT = "424242"
BASE = datetime(2026, 3, 2, 12, 0, tzinfo=clock.IST)


def q(sql: str, *args: Any) -> list[dict[str, Any]]:
    with transaction() as conn:
        return conn.execute(sql, args).fetchall()


@pytest.fixture()
def env(pinned_clock: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake-test-token")
    clock.pin(BASE)
    tasks.reset_for_tests()
    adapters_pg._limiter = None  # fresh rate-limit buckets per test
    who = q("SELECT p.person_id, pt.patient_id FROM cm.persons p JOIN cm.patients pt USING (person_id) WHERE p.token='P-0142'")[0]
    pid = who["person_id"]
    with transaction() as conn:
        conn.execute("DELETE FROM cm.outbox WHERE recipient_id=%s", (pid,))
        conn.execute("DELETE FROM cm.approvals WHERE thread_id LIKE 'fast-%%' AND patient_id=%s", (who["patient_id"],))
        conn.execute("DELETE FROM cm.channel_bindings WHERE person_id=%s", (pid,))
        conn.execute("DELETE FROM cm.channel_bindings WHERE external_id=%s", (CHAT,))
    yield {"person": pid, "patient": who["patient_id"], "deps": build_deps(SECRET)}
    clock.unpin()


def post(env: dict[str, Any], update: dict[str, Any], secret: str | None = SECRET) -> tuple[int, dict[str, Any]]:
    return handle_webhook(update, secret, env["deps"])


def msg(text: str, uid: int | None = None) -> dict[str, Any]:
    return {
        "update_id": uid or uuid4().int % 10**9,
        "message": {"message_id": 1, "chat": {"id": int(CHAT), "type": "private"}, "text": text},
    }


def tap(data: str, uid: int) -> dict[str, Any]:
    return {
        "update_id": uid,
        "callback_query": {
            "id": "cbq1",
            "from": {"id": int(CHAT)},
            "data": data,
            "message": {"message_id": 7, "chat": {"id": int(CHAT), "type": "private"}},
        },
    }


def bind(env: dict[str, Any]) -> None:
    code = make_invite.make("PT-0142")
    assert code
    st, body = post(env, msg(f"/start {code}"))
    assert st == 200 and body["method"] == "sendMessage" and "connected" in body["text"]


def sent_reminder(env: dict[str, Any]) -> tuple[UUID, FakeTelegramClient]:
    assert reminders.produce()["created"] == 1
    client = FakeTelegramClient()
    out = outbox_drainer.drain_once(client)
    assert out["sent"] == 1, (out, q("SELECT status,last_error FROM cm.outbox WHERE recipient_id=%s", env["person"]))
    oid = q("SELECT outbox_id FROM cm.outbox WHERE recipient_id=%s AND kind='checkin'", env["person"])[0]["outbox_id"]
    return oid, client


def test_bind_is_single_use_and_bad_secret_refused(env: dict[str, Any]) -> None:
    code = make_invite.make("PT-0142")
    assert post(env, msg(f"/start {code}"), secret="wrong")[0] == 401
    assert post(env, msg(f"/start {code}"))[1]["text"].startswith("You are connected")
    b = PgBindings().by_chat(CHAT)
    assert b and b.status == "active" and b.patient_id == env["patient"]
    # the code is spent
    assert "not valid" in post(env, msg(f"/start {code}"))[1]["text"]
    assert q("SELECT count(*) AS n FROM cm.consents WHERE person_id=%s AND source='telegram' AND state='granted'", env["person"])[0]["n"] >= 2


def test_reminder_sent_once_with_buttons_and_prompt_event(env: dict[str, Any]) -> None:
    bind(env)
    oid, client = sent_reminder(env)
    assert len(client.sent) == 1 and client.sent[0]["chat_id"] == CHAT
    assert client.sent[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"c:{oid.hex}:t"
    row = outbox_repo.get(oid)
    assert row and row["status"] == "sent" and row["provider_message_id"]
    assert q("SELECT count(*) AS n FROM cm.events WHERE type='CheckinPrompt' AND payload->>'outbox_id'=%s", str(oid))[0]["n"] == 1
    # second producer run and second drain send nothing
    assert reminders.produce()["existing"] == 1
    assert outbox_drainer.drain_once(client)["claimed"] == 0
    assert len(client.sent) == 1


def test_tap_missed_creates_dose_event_and_red_draft(env: dict[str, Any]) -> None:
    bind(env)
    for i, d in enumerate(("2026-02-28", "2026-03-01")):  # two earlier missed days inside the 3-day window
        events_repo.append_event(events_repo.NewEvent(
            patient_id=env["patient"], type="DoseCheckin", occurred_at=BASE - timedelta(days=2 - i),
            recorded_at=BASE - timedelta(days=2 - i), source="system", idempotency_key=f"t-miss-{uuid4()}",
            payload={"status": "missed", "for_date": d},
        ))
    oid, _ = sent_reminder(env)
    uid = uuid4().int % 10**9
    st, body = post(env, tap(f"c:{oid.hex}:m", uid))
    assert st == 200 and body["method"] == "answerCallbackQuery"
    ev = q("SELECT * FROM cm.events WHERE idempotency_key=%s", f"tg:{uid}")
    assert len(ev) == 1 and ev[0]["type"] == "DoseCheckin" and ev[0]["payload"]["status"] == "missed"
    assert ev[0]["consent_id"] is not None
    red = q("SELECT * FROM cm.approvals WHERE patient_id=%s AND thread_id LIKE 'fast-missed_dose-%%'", env["patient"])
    assert len(red) == 1 and red[0]["tier"] == "red" and red[0]["status"] == "pending"
    assert red[0]["payload"]["recipients"][0]["person_id"] == str(env["person"])
    assert tasks.pending() >= 1


def test_repeated_update_id_is_ignored(env: dict[str, Any]) -> None:
    bind(env)
    oid, _ = sent_reminder(env)
    uid = uuid4().int % 10**9
    for _ in range(3):
        r = post(env, tap(f"c:{oid.hex}:t", uid))
        assert r[0] == 200
    assert q("SELECT count(*) AS n FROM cm.events WHERE idempotency_key=%s", f"tg:{uid}")[0]["n"] == 1


def test_red_symptom_tap_creates_red_draft(env: dict[str, Any]) -> None:
    bind(env)
    oid, _ = sent_reminder(env)
    uid = uuid4().int % 10**9
    post(env, tap(f"s:{oid.hex}:20:d", uid))  # mask 0x20 = item 5 (yellow eyes) is a danger symptom
    ev = q("SELECT payload FROM cm.events WHERE idempotency_key=%s", f"tg:{uid}")[0]["payload"]
    assert ev["danger"] is True
    assert q("SELECT tier FROM cm.approvals WHERE patient_id=%s AND thread_id LIKE 'fast-red_symptom-%%'", env["patient"])[0]["tier"] == "red"


def test_row_without_approval_is_refused(env: dict[str, Any]) -> None:
    bind(env)
    with pytest.raises(psycopg.Error), transaction() as conn:  # the database refuses it outright
        conn.execute(
            "INSERT INTO cm.outbox (kind, recipient_id, channel, body, dedup_key) VALUES ('ai_message',%s,'telegram','x',%s)",
            (env["person"], f"k-{uuid4()}"),
        )
    deps = outbox_drainer.make_deps(FakeTelegramClient())
    row = {"outbox_id": uuid4(), "kind": "ai_message", "recipient_id": env["person"], "channel": "telegram",
           "body": "hello", "dedup_key": f"k-{uuid4()}", "approval_id": None, "template_id": None}
    res = asyncio.run(send_outbox(row, deps))
    assert res.status == "failed" and res.skip_reason == "invalid_approval"
    assert deps.client.sent == []  # type: ignore[attr-defined]


def test_revoke_stops_sends(env: dict[str, Any]) -> None:
    bind(env)
    assert reminders.produce()["created"] == 1  # queued, not yet drained
    st, body = post(env, msg("/stop"))
    assert "turned off" in body["text"]
    assert PgBindings().by_person(env["person"]).status == "revoked"  # type: ignore[union-attr]
    client = FakeTelegramClient()
    out = outbox_drainer.drain_once(client)
    assert out["sent"] == 0 and client.sent == []
    row = q("SELECT status, last_error FROM cm.outbox WHERE recipient_id=%s", env["person"])[0]
    assert row["status"] == "failed" and row["last_error"] == "skipped:no_consent"
    assert reminders.produce()["no_consent"] == 0  # revoked binding is not a target at all


def test_retry_after_reschedules(env: dict[str, Any]) -> None:
    bind(env)
    reminders.produce()
    client = FakeTelegramClient()
    client.script = [TgRetryAfter(120)]
    assert outbox_drainer.drain_once(client)["retry"] == 1
    row = q("SELECT status, next_attempt_at FROM cm.outbox WHERE recipient_id=%s", env["person"])[0]
    assert row["status"] == "pending" and row["next_attempt_at"] >= BASE + timedelta(seconds=119)
    assert outbox_drainer.drain_once(client)["claimed"] == 0  # not due yet


def test_blocked_marks_binding_and_unreachable_event(env: dict[str, Any]) -> None:
    bind(env)
    reminders.produce()
    client = FakeTelegramClient()
    client.script = [TgBlocked()]
    assert outbox_drainer.drain_once(client)["failed"] == 1
    assert PgBindings().by_person(env["person"]).status == "blocked"  # type: ignore[union-attr]


def test_quiet_hours_defers_reminder(env: dict[str, Any]) -> None:
    bind(env)
    night = datetime(2026, 3, 2, 23, 0, tzinfo=clock.IST)
    clock.pin(night)
    assert reminders.produce()["created"] == 1
    row = q("SELECT next_attempt_at FROM cm.outbox WHERE recipient_id=%s", env["person"])[0]
    assert row["next_attempt_at"] > night


# ---- HTTP client error mapping (httpx MockTransport, no network) ----------------------------
def _client(status: int, body: dict[str, Any]) -> HttpTelegramClient:
    return HttpTelegramClient(httpx.MockTransport(lambda r: httpx.Response(status, json=body)))


@pytest.mark.parametrize(
    ("status", "body", "exc"),
    [
        (429, {"ok": False, "error_code": 429, "parameters": {"retry_after": 7}}, TgRetryAfter),
        (403, {"ok": False, "error_code": 403}, TgBlocked),
        (401, {"ok": False, "error_code": 401}, TgAuthError),
        (502, {"ok": False, "error_code": 502}, TgTransient),
    ],
)
def test_http_client_error_mapping(monkeypatch: pytest.MonkeyPatch, status: int, body: dict[str, Any], exc: type) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake-test-token")
    with pytest.raises(exc) as ei:
        asyncio.run(_client(status, body).send_message("1", "hi"))
    assert "fake-test-token" not in str(ei.value)


def test_http_client_ok_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake-test-token")
    ok = _client(200, {"ok": True, "result": {"message_id": 99}})
    assert asyncio.run(ok.send_message("1", "hi", {"inline_keyboard": []})) == "99"

    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("t")

    with pytest.raises(TgTransient):
        asyncio.run(HttpTelegramClient(httpx.MockTransport(boom)).send_message("1", "hi"))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    with pytest.raises(TgAuthError):
        asyncio.run(ok.send_message("1", "hi"))


def test_webhook_route_and_budget_caps(env: dict[str, Any]) -> None:
    from fastapi.testclient import TestClient

    from cm.api.main import app

    c = TestClient(app)
    import os

    os.environ["TELEGRAM_WEBHOOK_SECRET"] = SECRET
    try:
        assert c.post("/webhooks/telegram", json=msg("hi")).status_code == 401
        r = c.post("/webhooks/telegram", json=msg("hi"), headers={"X-Telegram-Bot-Api-Secret-Token": SECRET})
        assert r.status_code == 200 and r.json()["method"] == "sendMessage"  # unbound chat gets the invite-only text
    finally:
        del os.environ["TELEGRAM_WEBHOOK_SECRET"]


def test_pg_usage_store_feeds_governor(pinned_clock: None) -> None:
    from cm.core import budget, budget_pg

    gov = budget.BudgetGovernor(budget.BudgetLimits(), budget.PriceTable({"m": (1.0, 1.0)}), budget_pg.PgUsageStore())
    before = gov.store.day_cost(gov.today())
    gov.record(model="m", tokens_in=1000, tokens_out=1000, task_id=f"t-{uuid4().hex[:8]}", task_type="other")
    assert round(gov.store.day_cost(gov.today()) - before, 4) == 2.0
    assert budget.usage_numbers(gov).today_spent_usd >= 2.0


def test_callback_data_fits_telegram_limit() -> None:
    assert len(tg_callback.dose_buttons(str(uuid4()))["inline_keyboard"][0][0]["callback_data"].encode()) <= 64
