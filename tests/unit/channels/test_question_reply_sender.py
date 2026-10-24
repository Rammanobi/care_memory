"""Unit: threaded question replies in the Telegram sender (fakes only, no database, no network)."""

import asyncio
from typing import Any
from uuid import uuid4

from cm.channels import question_routing as qr
from cm.channels import tg_sender
from cm.channels.tg_http import HttpTelegramClient
from cm.channels.tg_sender import send_outbox
from cm.router.banned import find_banned
from tests.unit.channels.test_telegram_lane import NIGHT, World

NL = chr(10) * 2


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def reply_row(w: World, *, priority: str = "normal", mid: int | None = 55, excerpt: str = "When is my visit?") -> dict:
    return w.outbox.add(
        {
            "recipient_id": w.person,
            "kind": "ai_message",
            "channel": "telegram",
            "body": "Your visit is on Monday.",
            "approval_id": uuid4(),
            "decision_id": uuid4(),
            "dedup_key": f"q:{uuid4()}",
            "meta": {
                "reply_to": {"approval_id": str(uuid4()), "question_excerpt": excerpt, "telegram_message_id": mid},
                "priority": priority,
            },
        }
    )


def test_effective_kind_only_for_rows_with_reply_to() -> None:
    assert tg_sender.effective_kind({"kind": "ai_message", "meta": {"reply_to": {}}}) == "question_reply"
    assert tg_sender.effective_kind({"kind": "ai_message", "meta": {}}) == "ai_message"
    assert tg_sender.effective_kind({"kind": "checkin", "meta": {"reply_to": {}}}) == "checkin"


def test_threaded_english_reply() -> None:
    w = World()
    d, c = w.sender()
    assert run(send_outbox(reply_row(w), d)).status == "sent"
    sent = c.sent[0]
    assert sent["reply_to_message_id"] == 55
    assert sent["text"] == 'Reply to your question: "When is my visit?"' + NL + "Your visit is on Monday."


def test_telugu_first_line() -> None:
    w = World()
    w.binding.lang = "te"
    d, c = w.sender()
    run(send_outbox(reply_row(w), d))
    assert c.sent[0]["text"].startswith('మీ ప్రశ్నకు సమాధానం: "When is my visit?"' + NL)
    assert not find_banned(c.sent[0]["text"])


def test_no_message_id_sends_unthreaded() -> None:
    w = World()
    d, c = w.sender()
    run(send_outbox(reply_row(w, mid=None), d))
    assert c.sent[0]["reply_to_message_id"] is None


def test_exempt_from_daily_cap_but_normal_message_is_capped() -> None:
    w = World()
    d, c = w.sender()
    for i in range(3):
        w.outbox.add({"recipient_id": w.person, "status": "sent", "kind": "ai_message", "dedup_key": f"o{i}"})
    assert run(send_outbox(reply_row(w), d)).status == "sent"
    other = w.prompt()
    assert run(send_outbox(other, d)).skip_reason == "rate_limit"


def test_quiet_hours_bypass_only_when_urgent() -> None:
    w = World(at=NIGHT)
    d, c = w.sender()
    calm = run(send_outbox(reply_row(w), d))
    assert calm.status == "retry" and calm.skip_reason == "quiet_hours"
    assert run(send_outbox(reply_row(w, priority="urgent"), d)).status == "sent"


def test_consent_and_banned_term_still_gate_a_reply() -> None:
    w = World(consent=False)
    d, c = w.sender()
    assert run(send_outbox(reply_row(w), d)).skip_reason == "no_consent"
    w2 = World()
    d2, c2 = w2.sender()
    bad = reply_row(w2)
    bad["body"] = "Take the TB tablets"
    assert run(send_outbox(bad, d2)).skip_reason == "banned_term" and c2.sent == []


def test_missing_approval_is_still_refused() -> None:
    w = World()
    d, c = w.sender()
    row = reply_row(w)
    row["approval_id"] = None
    assert run(send_outbox(row, d)).skip_reason == "invalid_approval" and c.sent == []


def test_excerpt_is_short_and_banned_term_clean() -> None:
    assert len(qr.excerpt("word " * 60)) <= 80 and qr.excerpt("word " * 60).endswith("...")
    assert qr.excerpt("my TB medicine") == ""
    assert qr.excerpt("  hello   there ") == "hello there"


def test_http_client_threads_with_reply_to_message_id(monkeypatch) -> None:  # noqa: ANN001
    import httpx

    seen: list[dict[str, Any]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        import json

        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 9}})

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake-test-token")
    cl = HttpTelegramClient(httpx.MockTransport(handler))
    assert run(cl.send_message("1", "hi", None, reply_to_message_id=55)) == "9"
    assert seen[0]["reply_to_message_id"] == 55 and seen[0]["allow_sending_without_reply"] is True
    run(cl.send_message("1", "hi"))
    assert "reply_to_message_id" not in seen[1]


def test_priority_to_tier_mapping() -> None:
    assert qr.priority_to_tier("urgent") == "red" and qr.priority_to_tier("high") == "amber"
    assert qr.priority_to_tier("normal") is None and qr.priority_to_tier(None) is None
