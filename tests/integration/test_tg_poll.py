"""Telegram polling: fake HTTP transport (httpx.MockTransport), no network."""

import asyncio
import inspect
import json
import logging
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

from cm.channels import telegram
from cm.channels.tg_client import TgRetryAfter
from cm.channels.tg_http import HttpTelegramClient, TgConflict
from cm.jobs import tg_poll
from cm.jobs.tg_poll import Poller
from tests.integration.test_telegram_pg import (  # noqa: F401
    CHAT,
    env,
    make_invite,
    q,
    sent_reminder,
    tap,
)
from tests.integration.test_telegram_pg import (
    TOKEN as PATIENT_TOKEN,
)

TOKEN = "123:fake-test-token"
SECRET_TEXT = "my private words"


class Fake:
    """Scripted Bot API. responses: method -> list of (status, json) popped in order, else ok."""

    def __init__(self, scripts: dict[str, list[tuple[int, Any]]] | None = None) -> None:
        self.scripts = scripts or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        self.calls.append((method, json.loads(request.content or b"{}")))
        q_ = self.scripts.get(method)
        if q_:
            status, body = q_.pop(0)
            return httpx.Response(status, json=body)
        return httpx.Response(
            200, json={"ok": True, "result": [] if method == "getUpdates" else True}
        )

    def names(self) -> list[str]:
        return [m for m, _ in self.calls]


def ok(result: Any) -> tuple[int, Any]:
    return 200, {"ok": True, "result": result}


@pytest.fixture(autouse=True)
def tok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TG_OFFSET_FILE", str(tmp_path / "off.json"))


def poller(fake: Fake, stop: threading.Event | None = None, handler: Any = None) -> Poller:
    async def nosleep(_s: float) -> None:
        return None

    return Poller(
        HttpTelegramClient(httpx.MockTransport(fake)), stop or threading.Event(), handler, nosleep
    )


def upd(uid: int) -> dict[str, Any]:
    return {
        "update_id": uid,
        "message": {"message_id": 1, "chat": {"id": 1, "type": "private"}, "text": SECRET_TEXT},
    }


def test_offset_advances_and_no_replay_after_restart() -> None:
    seen: list[int] = []

    def handler(raw: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        seen.append(raw["update_id"])
        return 200, {"ok": True}

    fake = Fake({"getUpdates": [ok([upd(10), upd(11)])]})
    p = poller(fake, handler=handler)
    assert asyncio.run(p.step()) == 2
    assert p.offset == 12 and json.loads(Path(tg_poll.offset_path()).read_text())["offset"] == 12
    fake2 = Fake()
    p2 = poller(fake2, handler=handler)  # "restart"
    asyncio.run(p2.step())
    assert fake2.calls[0][1]["offset"] == 12 and seen == [10, 11]


def test_start_deletes_webhook_without_dropping_updates() -> None:
    fake = Fake()
    asyncio.run(poller(fake).start())
    assert fake.calls == [("deleteWebhook", {"drop_pending_updates": False})]


def test_reply_is_applied_with_real_methods() -> None:
    reply = {"method": "answerCallbackQuery", "callback_query_id": "x", "text": "Noted"}
    fake = Fake({"getUpdates": [ok([upd(1)])]})
    asyncio.run(poller(fake, handler=lambda r: (200, reply)).step())
    assert fake.calls[-1] == ("answerCallbackQuery", {"callback_query_id": "x", "text": "Noted"})


def test_409_and_429_and_network_errors_back_off_then_continue() -> None:
    stop = threading.Event()
    fake = Fake(
        {
            "getUpdates": [
                (409, {"ok": False, "error_code": 409}),
                (429, {"ok": False, "error_code": 429, "parameters": {"retry_after": 3}}),
                (502, {"ok": False, "error_code": 502}),
                ok([upd(5)]),
            ]
        }
    )

    def handler(raw: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        stop.set()
        return 200, {"ok": True}

    p = poller(fake, stop, handler)
    sleeps: list[float] = []

    async def rec(s: float) -> None:
        sleeps.append(s)

    p._sleep = rec
    asyncio.run(p.run())
    assert p.offset == 6
    assert 3.0 in sleeps and len(sleeps) == 3
    assert fake.names().count("deleteWebhook") == 2  # start + after the 409


def test_error_types() -> None:
    fake = Fake(
        {
            "getUpdates": [
                (409, {"ok": False, "error_code": 409}),
                (429, {"ok": False, "parameters": {"retry_after": 7}, "error_code": 429}),
            ]
        }
    )
    c = HttpTelegramClient(httpx.MockTransport(fake))
    with pytest.raises(TgConflict):
        asyncio.run(c.get_updates(None))
    with pytest.raises(TgRetryAfter) as e:
        asyncio.run(c.get_updates(None))
    assert e.value.seconds == 7


def test_token_and_text_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    fake = Fake({"getUpdates": [(500, {"ok": False, "error_code": 500}), ok([upd(3)])]})
    stop = threading.Event()

    def handler(raw: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        stop.set()
        raise RuntimeError(f"boom {SECRET_TEXT}")  # a failing handler must not leak either

    asyncio.run(poller(fake, stop, handler).run())
    assert "tg update" in caplog.text and "update_id=3" in caplog.text
    assert TOKEN not in caplog.text and "fake-test-token" not in caplog.text
    assert SECRET_TEXT not in caplog.text and "boom" not in caplog.text


def test_trusted_path_not_reachable_from_route() -> None:
    import cm.api.routers.webhooks as wh

    assert "handle_local_poll" not in inspect.getsource(wh)
    assert not hasattr(wh, "handle_local_poll")

    # the webhook entry never accepts a missing/guessed header, whatever the deps secret
    class D:  # minimal deps stub: secret check happens before anything else is touched
        secret = ""

        class audit:  # noqa: N801
            @staticmethod
            def audit(*_a: Any, **_k: Any) -> None:
                return None

    assert telegram.handle_webhook(upd(1), None, D())[0] == 401  # type: ignore[arg-type]
    assert telegram.handle_webhook(upd(1), telegram._LOCAL_POLL_KEY[:-1], D())[0] == 401  # type: ignore[arg-type]


@pytest.mark.db
def test_update_becomes_event_row_via_poller(env: dict[str, Any]) -> None:  # noqa: F811
    code = make_invite.make(PATIENT_TOKEN)
    fake = Fake(
        {
            "getUpdates": [
                ok(
                    [
                        {
                            "update_id": 900,
                            "message": {
                                "message_id": 1,
                                "chat": {"id": int(CHAT), "type": "private"},
                                "text": f"/start {code}",
                            },
                        }
                    ]
                )
            ]
        }
    )
    p = poller(fake)
    asyncio.run(p.step())
    assert fake.calls[-1][0] == "sendMessage" and "connected" in fake.calls[-1][1]["text"]
    oid, _ = sent_reminder(env)
    fake2 = Fake({"getUpdates": [ok([tap(f"c:{oid.hex}:t", 901)])]})
    asyncio.run(poller(fake2).step())
    assert fake2.calls[-1][0] == "answerCallbackQuery"
    n = q("SELECT count(*) AS n FROM cm.events WHERE idempotency_key=%s", "tg:901")[0]["n"]
    assert n == 1
    # replay of the same update id is a no-op
    fake3 = Fake({"getUpdates": [ok([tap(f"c:{oid.hex}:t", 901)])]})
    asyncio.run(poller(fake3).step())
    assert q("SELECT count(*) AS n FROM cm.events WHERE idempotency_key=%s", "tg:901")[0]["n"] == 1
