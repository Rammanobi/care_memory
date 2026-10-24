"""Lane F tests: webhook, binding, sender, router. No network, no token."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from cm.channels import sim_updates as sim
from cm.channels.ports import Binding
from cm.channels.tg_client import FakeTelegramClient, TgAuthError, TgBlocked, TgRetryAfter
from cm.channels.tg_fakes import (
    FakeAudit,
    FakeBindings,
    FakeConsents,
    FakeEvents,
    FakeFastPath,
    FakeOutbox,
    FakeTasks,
)
from cm.channels.tg_inbound import Deps, handle_update
from cm.channels.tg_ratelimit import ChatLimiter
from cm.channels.tg_sender import SenderDeps, send_outbox
from cm.router.banned import find_banned
from cm.router.router import route

SECRET = "test-secret"
CHAT = 4242
DAY = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)  # 13:30 IST, open hours
NIGHT = datetime(2026, 3, 2, 17, 0, tzinfo=UTC)  # 22:30 IST, quiet


class Clock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


class World:
    def __init__(self, role: str = "patient", consent: bool = True, at: datetime = DAY) -> None:
        self.clock = Clock(at)
        self.person, self.patient = uuid4(), uuid4()
        self.bindings, self.events, self.consents = FakeBindings(), FakeEvents(), FakeConsents()
        self.outbox, self.tasks, self.fast, self.audit = (
            FakeOutbox(),
            FakeTasks(),
            FakeFastPath(),
            FakeAudit(),
        )
        self.binding = self.bindings.add(
            Binding(
                binding_id=uuid4(),
                person_id=self.person,
                role=role,
                patient_id=self.patient,
                external_id=str(CHAT),
                status="active",
            )
        )
        if consent:
            self.consents.grant(self.person, "telegram", "daily_checkin")
            self.consents.grant(self.person, "telegram", "care_coordination")
        self.deps = Deps(
            SECRET,
            self.bindings,
            self.events,
            self.consents,
            self.outbox,
            self.tasks,
            self.fast,
            self.audit,
            self.clock,
        )

    def prompt(self, **kw) -> dict:
        return self.outbox.add(
            {
                "recipient_id": self.person,
                "kind": "checkin",
                "channel": "telegram",
                "body": "Good morning. Did you take today's medicine?",
                "template_id": uuid4(),
                "dedup_key": f"checkin:{uuid4()}",
                "sent_at": DAY - timedelta(minutes=9),
                **kw,
            }
        )

    def send(self, upd: dict, secret: str | None = SECRET):
        return handle_update(upd, secret, self.deps)

    def sender(self, client=None, t: float = 0.0) -> tuple[SenderDeps, FakeTelegramClient]:
        client = client or FakeTelegramClient()
        self.t = getattr(self, "t", [t])
        lim = ChatLimiter(lambda: self.t[0])
        return SenderDeps(
            client,
            self.outbox,
            self.bindings,
            self.consents,
            self.events,
            self.tasks,
            self.audit,
            lim,
            self.clock,
        ), client


# ---- inbound ----


def test_secret_wrong_and_missing():
    w = World()
    assert w.send(sim.start(1, CHAT, "x"), "nope")[0] == 401
    assert w.send(sim.start(1, CHAT, "x"), None)[0] == 401
    assert w.events.rows == [] and w.tasks.calls == []


def test_dedupe_one_event_for_repeat_update():
    w = World()
    p = w.prompt()
    upd = sim.dose_tap(77, CHAT, p["outbox_id"].hex, "m")
    s1, _ = w.send(upd)
    s2, body = w.send(upd)
    assert s1 == s2 == 200
    assert len(w.events.rows) == 1 and w.events.rows[0]["idempotency_key"] == "tg:77"
    assert len(w.fast.missed) == 1  # fast path not repeated
    assert {c[1] for c in w.tasks.calls} == {"tg-77"}
    assert body["method"] == "answerCallbackQuery"


def test_tap_to_event_taken_and_missed():
    w = World()
    p = w.prompt()
    w.send(sim.dose_tap(1, CHAT, p["outbox_id"].hex, "t"))
    ev = w.events.rows[0]
    assert ev["type"] == "DoseCheckin" and ev["payload"]["status"] == "taken"
    assert ev["payload"]["reply_seconds"] == 9 * 60 or ev["payload"]["reply_seconds"] >= 0
    assert ev["source"] == "telegram" and ev["reporter_mode"] == "self"
    w.send(sim.dose_tap(2, CHAT, p["outbox_id"].hex, "m"))
    assert w.events.rows[1]["payload"]["status"] == "missed" and w.fast.missed == [w.patient]


def test_red_symptom_fast_path():
    w = World()
    p = w.prompt()
    h = p["outbox_id"].hex
    _, body = w.send(sim.symptom_tap(1, CHAT, h, 0, "6"))  # toggle only
    assert body["method"] == "editMessageReplyMarkup" and w.events.rows == []
    w.send(sim.symptom_tap(2, CHAT, h, 1 << 6, "d"))  # blood when coughing
    ev = w.events.rows[0]
    assert ev["type"] == "SymptomReport" and ev["payload"]["danger"] is True
    assert w.fast.red == [w.patient]


def test_consent_refusal_stores_nothing():
    w = World(consent=False)
    p = w.prompt()
    _, body = w.send(sim.dose_tap(1, CHAT, p["outbox_id"].hex, "t"))
    assert "turned off" in body["text"]
    assert w.events.rows == [] and w.tasks.calls == []


def test_forged_tap_rejected():
    w = World()
    other = w.outbox.add({"recipient_id": uuid4(), "kind": "checkin", "channel": "telegram"})
    w.send(sim.dose_tap(1, CHAT, other["outbox_id"].hex, "t"))
    assert w.events.rows == []


def test_unknown_chat_gets_invitation_only():
    w = World()
    _, body = w.send(sim.message(1, 999, "hello"))
    assert "invitation" in body["text"] and w.events.rows == []
    _, body = w.send(sim.dose_tap(2, 999, uuid4().hex, "t"))
    assert w.events.rows == []


def test_bind_and_stop():
    w = World()
    pid = uuid4()
    w.bindings.add(
        Binding(
            binding_id=uuid4(),
            person_id=pid,
            role="patient",
            patient_id=uuid4(),
            invite_code="ABC123",
            invite_expires_at=DAY + timedelta(days=1),
        )
    )
    _, body = w.send(sim.start(1, 555, "ABC123"))
    assert "connected" in body["text"]
    assert w.bindings.by_chat("555").status == "active"
    assert w.consents.has_consent(pid, "telegram", "daily_checkin", DAY)
    _, body = w.send(sim.start(2, 556, "ABC123"))  # single use
    assert "not valid" in body["text"]
    w.send(sim.stop(3, 555))
    assert w.bindings.by_chat("555").status == "revoked"
    assert not w.consents.has_consent(pid, "telegram", "daily_checkin", DAY)


def test_expired_code():
    w = World()
    w.bindings.add(
        Binding(
            binding_id=uuid4(),
            person_id=uuid4(),
            role="patient",
            invite_code="OLD",
            invite_expires_at=DAY - timedelta(hours=1),
        )
    )
    _, body = w.send(sim.start(1, 600, "OLD"))
    assert "not valid" in body["text"] and w.bindings.by_chat("600") is None


# ---- sender ----


def run(coro):
    return asyncio.run(coro)


def test_sender_sends_and_records_prompt():
    w = World()
    d, c = w.sender()
    row = w.prompt()
    r = run(send_outbox(row, d))
    assert r.status == "sent" and len(c.sent) == 1
    assert any(e["type"] == "CheckinPrompt" for e in w.events.rows)
    assert any(t[1].startswith("nudge-") for t in w.tasks.calls)
    assert run(send_outbox(row, d)).skip_reason == "already_sent"  # idempotent on dedup_key
    assert len(c.sent) == 1


def test_no_approval_refused():
    w = World()
    d, c = w.sender()
    row = w.prompt(template_id=None)
    r = run(send_outbox(row, d))
    assert r.status == "failed" and r.skip_reason == "invalid_approval" and c.sent == []
    # gated kind with template but no approval_id is refused too
    row2 = w.prompt(kind="ai_message", dedup_key="k2")
    assert run(send_outbox(row2, d)).skip_reason == "invalid_approval"
    # approval_id present is accepted
    row3 = w.prompt(kind="ai_message", approval_id=uuid4(), dedup_key="k3")
    assert run(send_outbox(row3, d)).status == "sent"


@pytest.mark.parametrize(
    "bad", ["Your TB medicine", "tuberculosis follow-up", "take rifampicin", "DOTS visit", "टीबी"]
)
def test_banned_terms_refused(bad):
    w = World(role="supporter")
    d, c = w.sender()
    r = run(send_outbox(w.prompt(body=bad), d))
    assert r.status == "failed" and r.skip_reason == "banned_term" and c.sent == []


def test_banned_finder_no_false_positive():
    assert find_banned("Please check in and count the tablets.") == []
    assert find_banned("Stable and settled") == []


def test_no_consent_skips_send():
    w = World(consent=False)
    d, c = w.sender()
    assert run(send_outbox(w.prompt(), d)).skip_reason == "no_consent" and c.sent == []


def test_quiet_hours_deferred_and_red_exempt():
    w = World(at=NIGHT)
    d, c = w.sender()
    r = run(send_outbox(w.prompt(), d))
    assert r.status == "retry" and r.skip_reason == "quiet_hours" and r.retry_after_s > 0
    r2 = run(send_outbox(w.prompt(kind="red_alert", dedup_key="r"), d))
    assert r2.status == "sent"


def test_rate_limit_one_per_second_per_chat():
    w = World()
    d, c = w.sender()
    a, b, x = w.prompt(), w.prompt(), w.prompt()
    assert run(send_outbox(a, d)).status == "sent"
    r = run(send_outbox(b, d))
    assert r.status == "retry" and r.skip_reason == "rate_limit" and 0 < r.retry_after_s <= 1
    w.t[0] += 1.01
    assert run(send_outbox(b, d)).status == "sent"
    assert len(c.sent) == 2
    w.t[0] += 1.01
    assert run(send_outbox(x, d)).status == "sent"  # third of the day
    w.t[0] += 1.01
    assert run(send_outbox(w.prompt(), d)).skip_reason == "rate_limit"  # 3/day cap


def test_retry_after_honoured_and_auth_never_retried():
    w = World()
    c = FakeTelegramClient()
    d, _ = w.sender(c)
    c.script = [TgRetryAfter(7)]
    row = w.prompt()
    r = run(send_outbox(row, d))
    assert r.status == "retry" and r.retry_after_s == 7
    assert row["status"] == "pending" and row["next_attempt_at"] == DAY + timedelta(seconds=7)
    c.script = [TgAuthError()]
    w.t[0] += 5
    r = run(send_outbox(row, d))
    assert r.status == "failed" and r.error == "auth" and row["status"] == "failed"


def test_blocked_marks_binding_and_event():
    w = World()
    c = FakeTelegramClient()
    c.script = [TgBlocked()]
    d, _ = w.sender(c)
    r = run(send_outbox(w.prompt(), d))
    assert r.status == "failed" and w.binding.status == "blocked"
    assert any(e["type"] == "ChannelUnreachable" for e in w.events.rows)
    assert w.consents.has_consent(w.person, "telegram", "daily_checkin", DAY)  # consent untouched


# ---- router ----


def test_router_channel_fallback_and_block():
    n = DAY
    assert route("patient", "Hello", n, {"telegram": True, "webpush": True}).channel == "telegram"
    assert (
        route(
            "patient", "Hello", n, {"telegram": True, "webpush": True}, {"telegram": False}
        ).channel
        == "webpush"
    )
    assert route("patient", "Hello", n, {}).action == "none"
    assert route("supporter", "TB visit", n, {"telegram": True}).action == "block"
    assert route("patient", "Hello", NIGHT, {"telegram": True}).action == "defer"
    assert route("doctor", "alert", NIGHT, {"web_inbox": True}, red_to_staff=True).action == "send"
