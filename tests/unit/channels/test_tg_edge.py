"""Edge cases for the Telegram lane. Fakes only: no Telegram API, no database, no real clock."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from cm.channels import sim_updates as sim
from cm.channels import tg_callback as cb
from cm.channels.ports import Binding
from cm.channels.tg_client import FakeTelegramClient, TgBlocked, TgRetryAfter, TgTransient
from cm.channels.tg_http import HttpTelegramClient, map_response
from cm.channels.tg_sender import send_outbox
from cm.router.banned import find_banned
from cm.router.quiet_hours import IST, in_quiet_hours, next_open
from tests.unit.channels.test_telegram_lane import CHAT, DAY, World


@pytest.fixture(autouse=True)
def _real_quiet_hours(monkeypatch):
    """A dev .env may set the demo override; the edge tests assert the real 21:00-07:00 IST rule."""
    monkeypatch.delenv("DEMO_IGNORE_QUIET_HOURS", raising=False)


def run(coro):
    return asyncio.run(coro)


def ist(h: int, m: int = 0, s: int = 0) -> datetime:
    return datetime(2026, 3, 2, h, m, s, tzinfo=IST).astimezone(UTC)


# ---- webhook secret / shape ----


@pytest.mark.parametrize("bad", ["", " ", "test-secret ", "TEST-SECRET", "test-secre", "x" * 5000])
def test_secret_near_misses_rejected(bad):
    w = World()
    assert w.send(sim.start(1, CHAT, "x"), bad)[0] == 401
    assert w.events.rows == [] and w.tasks.calls == []
    assert w.audit.rows[-1][0] == "tg_bad_secret"


def test_empty_server_secret_never_authenticates():
    w = World()
    w.deps.secret = ""
    assert w.send(sim.start(1, CHAT, "x"), "")[0] == 401
    assert w.send(sim.start(1, CHAT, "x"), None)[0] == 401


@pytest.mark.parametrize("raw", [{}, {"update_id": "abc"}, {"foo": 1}, {"update_id": None}])
def test_malformed_update_acked_200_no_effect(raw):
    w = World()
    assert w.send(raw)[0] == 200
    assert w.events.rows == [] and w.tasks.calls == []


def test_update_with_neither_message_nor_callback_is_acked():
    w = World()
    assert w.send({"update_id": 5, "my_chat_member": {"x": 1}}) == (200, {"ok": True})


# ---- duplicate update ids ----


def test_duplicate_free_text_update_same_task_name():
    w = World()
    upd = sim.message(31, CHAT, "I have a question")
    w.send(upd)
    w.send(upd)
    # The task name is the dedupe key (Cloud Tasks drops the repeat): both calls use one name.
    assert {c[1] for c in w.tasks.calls} == {"tg-31"}


def test_duplicate_symptom_update_single_event_and_single_red():
    w = World()
    h = w.prompt()["outbox_id"].hex
    upd = sim.symptom_tap(9, CHAT, h, 1 << 6, "d")
    w.send(upd)
    w.send(upd)
    assert len(w.events.rows) == 1 and len(w.fast.red) == 1


# ---- /start codes ----


@pytest.mark.parametrize("code", ["", "   ", "NOPE", "abc123", "A" * 4000, "తెలుగు", "'; DROP TABLE x;--"])
def test_unknown_start_code(code):
    w = World()
    n = len(w.bindings.rows)
    _, body = w.send(sim.start(1, 777, code))
    assert "connected" not in body["text"]
    assert w.bindings.by_chat("777") is None and len(w.bindings.rows) == n


def test_start_code_is_case_sensitive_and_exact():
    w = World()
    w.bindings.add(Binding(binding_id=uuid4(), person_id=uuid4(), role="patient", invite_code="ABC123", invite_expires_at=DAY + timedelta(days=1)))
    assert "not valid" in w.send(sim.start(1, 700, "abc123"))[1]["text"]
    assert "connected" in w.send(sim.start(2, 700, "ABC123"))[1]["text"]


def test_invite_expiring_exactly_now_is_expired():
    w = World()
    w.bindings.add(Binding(binding_id=uuid4(), person_id=uuid4(), role="patient", invite_code="EDGE", invite_expires_at=DAY))
    assert "not valid" in w.send(sim.start(1, 701, "EDGE"))[1]["text"]


def test_used_invite_cannot_rebind_second_chat():
    w = World()
    w.bindings.add(Binding(binding_id=uuid4(), person_id=uuid4(), role="patient", invite_code="ONCE", invite_expires_at=DAY + timedelta(hours=1)))
    assert "connected" in w.send(sim.start(1, 800, "ONCE"))[1]["text"]
    assert "not valid" in w.send(sim.start(2, 801, "ONCE"))[1]["text"]
    assert w.bindings.by_chat("801") is None


def test_supporter_bind_grants_only_care_coordination():
    w = World()
    pid = uuid4()
    w.bindings.add(Binding(binding_id=uuid4(), person_id=pid, role="supporter", invite_code="SUP", invite_expires_at=DAY + timedelta(hours=1)))
    w.send(sim.start(1, 802, "SUP"))
    assert w.consents.has_consent(pid, "telegram", "care_coordination", DAY)
    assert not w.consents.has_consent(pid, "telegram", "daily_checkin", DAY)


def test_stop_from_unbound_chat_is_harmless():
    w = World()
    _, body = w.send(sim.stop(1, 12345))
    assert "invitation" in body["text"]
    assert w.binding.status == "active"


# ---- /stop then outbound ----


def test_stop_then_reminder_not_sent_and_tap_refused():
    w = World()
    p = w.prompt()
    w.send(sim.stop(1, CHAT))
    d, c = w.sender()
    r = run(send_outbox(w.prompt(), d))
    assert r.skip_reason == "no_consent" and c.sent == []
    _, body = w.send(sim.dose_tap(2, CHAT, p["outbox_id"].hex, "t"))
    assert "turned off" in body["text"] and w.events.rows == []


def test_stop_then_free_text_gets_stopped_text_and_no_task():
    w = World()
    w.send(sim.stop(1, CHAT))
    _, body = w.send(sim.message(2, CHAT, "hello again"))
    assert "turned off" in body["text"] and w.tasks.calls == []


# ---- unbound / non-text / long / group ----


def test_unbound_chat_every_message_kind_creates_nothing():
    w = World()
    for i, text in enumerate(["hello", "/help", "/start", "టీబీ ఉందా", "x" * 10000]):
        _, body = w.send(sim.message(i + 1, 999, text))
        assert "invitation" in body["text"]
    assert w.events.rows == [] and w.tasks.calls == []


def test_non_text_messages_do_not_crash():
    w = World()
    extras = [{"photo": [{"file_id": "a"}]}, {"voice": {"file_id": "v"}}, {"sticker": {}}, {"location": {"latitude": 1, "longitude": 2}}, {"text": None}]
    for i, extra in enumerate(extras):
        upd = sim.message(i + 1, CHAT, "")
        upd["message"].pop("text")
        upd["message"].update(extra)
        assert w.send(upd)[0] == 200
    assert w.events.rows == []


def test_message_without_chat_is_ignored():
    w = World()
    assert w.send({"update_id": 3, "message": {"text": "hi"}}) == (200, {"ok": True})


def test_group_chat_messages_ignored():
    w = World()
    assert w.send(sim.message(1, -100500, "/start X", chat_type="group")) == (200, {"ok": True})
    assert w.send(sim.message(2, -100500, "hi", chat_type="supergroup")) == (200, {"ok": True})
    assert w.tasks.calls == []


def test_very_long_and_telugu_text_handed_to_intake_intact():
    w = World()
    te = "నాకు దగ్గు ఎక్కువగా ఉంది " * 400
    w.send(sim.message(1, CHAT, te))
    w.send(sim.message(2, CHAT, "a" * 20000))
    assert w.tasks.calls[0][2]["text"] == te.strip()
    assert len(w.tasks.calls[1][2]["text"]) == 20000
    assert w.events.rows == []  # free text never writes an event inline


def test_whitespace_only_text_does_not_crash():
    w = World()
    assert w.send(sim.message(1, CHAT, "   \n  "))[0] == 200


# ---- callbacks: stale / forged / malformed ----

_Z = "0" * 32
BAD_DATA = [
    None,
    "",
    "garbage",
    "c::t",
    "c:nothex:t",
    "c:" + "g" * 32 + ":t",
    "c:" + "A" * 32 + ":t",
    "s:" + _Z + ":zz:1",
    "s:" + _Z + ":1ff:1",
    "s:" + _Z + ":01:9",
    "x" * 80,
    "c:" + _Z + ":t:extra",
    "తెలుగు",
]


@pytest.mark.parametrize("data", BAD_DATA)
def test_malformed_callback_data_rejected_no_crash(data):
    w = World()
    status, body = w.send(sim.tap(1, CHAT, data))
    assert status == 200 and body["method"] == "answerCallbackQuery"
    assert w.events.rows == []


def test_callback_for_unknown_or_stale_prompt_rejected():
    w = World()
    status, body = w.send(sim.dose_tap(1, CHAT, uuid4().hex, "t"))
    assert status == 200 and "not valid" in body["text"] and w.events.rows == []
    assert any(a[0] == "tg_forged_tap" for a in w.audit.rows)


def test_callback_unknown_dose_code_creates_no_event():
    w = World()
    h = w.prompt()["outbox_id"].hex
    w.send(sim.dose_tap(1, CHAT, h, "z"))
    assert w.events.rows == []


def test_callback_from_unbound_chat_refused():
    w = World()
    h = w.prompt()["outbox_id"].hex
    _, body = w.send(sim.dose_tap(1, 31337, h, "m"))
    assert "invitation" in body["text"] and w.events.rows == [] and w.fast.missed == []


def test_callback_from_group_ignored():
    w = World()
    h = w.prompt()["outbox_id"].hex
    upd = sim.dose_tap(1, CHAT, h, "m")
    upd["callback_query"]["message"]["chat"]["type"] = "group"
    assert w.send(upd) == (200, {"ok": True}) and w.events.rows == []


def test_callback_without_message_uses_sender_id():
    w = World()
    h = w.prompt()["outbox_id"].hex
    upd = sim.dose_tap(1, CHAT, h, "t")
    del upd["callback_query"]["message"]
    status, body = w.send(upd)
    assert status == 200 and body["method"] == "answerCallbackQuery"
    assert len(w.events.rows) == 1


def test_callback_without_any_chat_or_sender_does_not_500():
    w = World()
    upd = {"update_id": 4, "callback_query": {"id": "q", "data": "c:" + _Z + ":t"}}
    assert w.send(upd)[0] == 200
    assert w.events.rows == []


def test_other_persons_prompt_forged_symptom_rejected():
    w = World()
    other = w.outbox.add({"recipient_id": uuid4(), "kind": "checkin", "channel": "telegram"})
    w.send(sim.symptom_tap(1, CHAT, other["outbox_id"].hex, 0xFF, "d"))
    assert w.events.rows == [] and w.fast.red == []


def test_symptom_none_clears_mask_and_is_not_danger():
    w = World()
    h = w.prompt()["outbox_id"].hex
    w.send(sim.tap(1, CHAT, f"s:{h}:00:n"))
    ev = w.events.rows[0]
    assert ev["payload"]["items"] == [] and ev["payload"]["danger"] is False and w.fast.red == []


def test_symptom_non_danger_only_no_red():
    w = World()
    h = w.prompt()["outbox_id"].hex
    w.send(sim.symptom_tap(1, CHAT, h, 0b00000111, "d"))
    assert w.events.rows[0]["payload"]["danger"] is False and w.fast.red == []


def test_symptom_toggle_flips_bit_both_ways():
    w = World()
    h = w.prompt()["outbox_id"].hex
    _, b1 = w.send(sim.symptom_tap(1, CHAT, h, 0, "3"))
    assert "[x] " in b1["reply_markup"]["inline_keyboard"][3][0]["text"]
    _, b2 = w.send(sim.symptom_tap(2, CHAT, h, 1 << 3, "3"))
    assert "[x] " not in b2["reply_markup"]["inline_keyboard"][3][0]["text"]


def test_callback_data_within_64_bytes_for_every_button():
    h = uuid4().hex
    for row in cb.symptom_keyboard(h, 0xFF)["inline_keyboard"] + cb.dose_buttons(h)["inline_keyboard"]:
        for b in row:
            assert len(b["callback_data"].encode()) <= 64
            assert cb.parse(b["callback_data"]) is not None


def test_late_reply_flagged_and_negative_clock_skew_clamped():
    w = World()
    p = w.prompt(sent_at=DAY - timedelta(hours=3))
    w.send(sim.dose_tap(1, CHAT, p["outbox_id"].hex, "t"))
    assert w.events.rows[0]["payload"]["late"] is True
    p2 = w.prompt(sent_at=DAY + timedelta(minutes=5))  # sent "in the future"
    w.send(sim.dose_tap(2, CHAT, p2["outbox_id"].hex, "t"))
    assert w.events.rows[1]["payload"]["reply_seconds"] == 0


# ---- quiet hours boundaries (IST) ----


@pytest.mark.parametrize(
    ("h", "m", "s", "quiet"),
    [(20, 59, 59, False), (21, 0, 0, True), (23, 59, 59, True), (0, 0, 0, True), (6, 59, 59, True), (7, 0, 0, False), (12, 0, 0, False)],
)
def test_quiet_hours_boundaries(h, m, s, quiet):
    assert in_quiet_hours(ist(h, m, s)) is quiet


def test_next_open_from_boundaries():
    assert next_open(ist(21, 0)) == ist(7, 0) + timedelta(days=1)
    assert next_open(ist(6, 59, 59)) == ist(7, 0)
    assert next_open(ist(7, 0)) == ist(7, 0)
    assert next_open(ist(20, 59, 59)) == ist(20, 59, 59)
    assert next_open(ist(0, 0)) == ist(7, 0)


def test_sender_defers_at_21_00_and_sends_at_20_59_59_and_07_00():
    for t, expect in [(ist(21, 0), "retry"), (ist(6, 59, 59), "retry"), (ist(20, 59, 59), "sent"), (ist(7, 0), "sent")]:
        w = World(at=t)
        d, c = w.sender()
        r = run(send_outbox(w.prompt(), d))
        assert r.status == expect, t
        if expect == "retry":
            assert r.skip_reason == "quiet_hours" and r.retry_after_s > 0 and c.sent == []


@pytest.mark.parametrize("kind", ["red_alert", "escalation_notice", "danger_ack"])
def test_exempt_kinds_bypass_quiet_hours(kind):
    w = World(at=ist(23, 30))
    d, c = w.sender()
    assert run(send_outbox(w.prompt(kind=kind, dedup_key=kind), d)).status == "sent"


def test_exempt_kind_still_needs_consent_and_clean_text():
    w = World(at=ist(23, 30), consent=False)
    d, c = w.sender()
    assert run(send_outbox(w.prompt(kind="red_alert", dedup_key="r"), d)).skip_reason == "no_consent"
    w2 = World(at=ist(23, 30))
    d2, c2 = w2.sender()
    assert run(send_outbox(w2.prompt(kind="red_alert", body="tuberculosis alert", dedup_key="r"), d2)).skip_reason == "banned_term"
    assert c2.sent == []


# ---- daily cap ----


def test_daily_cap_is_three():
    w = World()
    d, c = w.sender()
    for _ in range(3):
        assert run(send_outbox(w.prompt(), d)).status == "sent"
        w.t[0] += 1.5
    r = run(send_outbox(w.prompt(), d))
    assert r.status == "skipped" and r.skip_reason == "rate_limit" and len(c.sent) == 3


def test_cap_is_per_recipient():
    w = World()
    d, c = w.sender()
    for _ in range(3):
        run(send_outbox(w.prompt(), d))
        w.t[0] += 1.5
    p2 = uuid4()
    w.bindings.add(Binding(binding_id=uuid4(), person_id=p2, role="patient", patient_id=uuid4(), external_id="555", status="active"))
    w.consents.grant(p2, "telegram", "daily_checkin")
    assert run(send_outbox(w.prompt(recipient_id=p2), d)).status == "sent"


# ---- retries: fakes and mocked transport ----


def test_retry_after_then_success_is_not_double_sent():
    w = World()
    c = FakeTelegramClient()
    c.script = [TgRetryAfter(3)]
    d, _ = w.sender(c)
    row = w.prompt()
    assert run(send_outbox(row, d)).status == "retry"
    w.t[0] += 5
    assert run(send_outbox(row, d)).status == "sent"
    assert len(c.sent) == 1
    assert run(send_outbox(row, d)).skip_reason == "already_sent"


def test_transient_5xx_retries_in_30s_then_recovers():
    w = World()
    c = FakeTelegramClient()
    c.script = [TgTransient("telegram 502"), TgTransient("telegram 503")]
    d, _ = w.sender(c)
    row = w.prompt()
    r = run(send_outbox(row, d))
    assert r.status == "retry" and r.retry_after_s == 30 and row["next_attempt_at"] == DAY + timedelta(seconds=30)
    w.t[0] += 5
    assert run(send_outbox(row, d)).status == "retry"
    w.t[0] += 5
    assert run(send_outbox(row, d)).status == "sent"
    assert len(c.sent) == 1


def test_blocked_user_not_retried_and_next_send_skipped():
    w = World()
    c = FakeTelegramClient()
    c.script = [TgBlocked()]
    d, _ = w.sender(c)
    assert run(send_outbox(w.prompt(), d)).error == "blocked"
    w.t[0] += 5
    assert run(send_outbox(w.prompt(), d)).skip_reason == "no_consent"  # binding blocked
    assert len(c.sent) == 0


@pytest.mark.parametrize(
    ("status", "data", "exc"),
    [
        (429, {"ok": False, "error_code": 429, "parameters": {"retry_after": 9}}, TgRetryAfter),
        (500, {"ok": False, "error_code": 500}, TgTransient),
        (502, None, TgTransient),
        (503, {"ok": False}, TgTransient),
        (409, {"ok": False, "error_code": 409}, TgTransient),
        (400, {"ok": False, "error_code": 400}, TgTransient),
    ],
)
def test_map_response_errors(status, data, exc):
    with pytest.raises(exc):
        map_response(status, data)


def test_map_response_429_without_parameters_defaults_to_1s():
    with pytest.raises(TgRetryAfter) as e:
        map_response(429, {"ok": False, "error_code": 429})
    assert e.value.seconds == 1.0


def test_http_client_mocked_transport_5xx_and_429_never_leak_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "000:FAKE-TEST-TOKEN")
    seq = [
        httpx.Response(429, json={"ok": False, "error_code": 429, "parameters": {"retry_after": 4}}),
        httpx.Response(502, text="bad gateway"),
        httpx.Response(200, json={"ok": True, "result": {"message_id": 7}}),
    ]
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        return seq[len(calls) - 1]

    cl = HttpTelegramClient(transport=httpx.MockTransport(handler))
    with pytest.raises(TgRetryAfter) as e1:
        run(cl.send_message("1", "hi"))
    assert e1.value.seconds == 4
    with pytest.raises(TgTransient) as e2:
        run(cl.send_message("1", "hi"))
    assert "FAKE-TEST-TOKEN" not in str(e2.value)
    assert run(cl.send_message("1", "hi")) == "7"


def test_http_client_network_error_wrapped_without_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "000:FAKE-TEST-TOKEN")

    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("conn refused for " + str(req.url))

    cl = HttpTelegramClient(transport=httpx.MockTransport(boom))
    with pytest.raises(TgTransient) as e:
        run(cl.send_message("1", "hi"))
    assert "FAKE-TEST-TOKEN" not in str(e.value)


def test_http_client_missing_token_is_auth_error(monkeypatch):
    from cm.channels.tg_client import TgAuthError

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    cl = HttpTelegramClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True})))
    with pytest.raises(TgAuthError):
        run(cl.send_message("1", "hi"))


def test_apply_reply_ignores_unknown_methods(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "000:FAKE-TEST-TOKEN")
    calls: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        calls.append("x")
        return httpx.Response(200, json={"ok": True})

    cl = HttpTelegramClient(transport=httpx.MockTransport(handler))
    run(cl.apply_reply({"method": "deleteMyCommands"}))
    run(cl.apply_reply({"text": "no method"}))
    assert calls == []


# ---- banned terms ----


@pytest.mark.parametrize("bad", ["క్షయ", "टीबी", "क्षय रोग", "T.B.", "t b", "HRZE", "Isoniazid", "RIFAMPICIN", "Dots", "AKT"])
def test_banned_variants_blocked_for_patient_send(bad):
    w = World()
    d, c = w.sender()
    r = run(send_outbox(w.prompt(body=f"Hello {bad} today"), d))
    assert r.skip_reason == "banned_term" and c.sent == []


def test_symptom_keyboard_labels_are_clean():
    for s in cb.SYMPTOMS:
        assert find_banned(s) == []
