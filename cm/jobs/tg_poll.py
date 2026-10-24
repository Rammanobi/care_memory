"""Integration: Telegram long polling for a laptop with no public URL.

    python -m cm.jobs.tg_poll

Calls deleteWebhook first (a bot cannot poll while a webhook is set), then loops getUpdates. Each raw update
goes to the same inbound handler as the webhook, through the trusted local path (no secret header: the poller
proves itself by holding the bot token). Replies are applied as real Bot API calls. The offset is saved under
out/ after every update so a restart does not replay. Logs carry update_id and type only: never the token or text.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cm.channels.adapters_pg import build_deps
from cm.channels.telegram import handle_local_poll
from cm.channels.tg_client import TgAuthError, TgError, TgRetryAfter
from cm.channels.tg_http import HttpTelegramClient, TgConflict
from cm.core.config import load_dotenv
from cm.core.logging import get_logger

log = get_logger()
LONG_POLL_S = 25
BACKOFF_MAX = 30.0


def offset_path() -> Path:
    return Path(os.environ.get("TG_OFFSET_FILE") or "out/tg_offset.json")


def load_offset() -> int | None:
    try:
        return int(json.loads(offset_path().read_text(encoding="utf-8"))["offset"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_offset(offset: int) -> None:
    p = offset_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"offset": offset}), encoding="utf-8")
    tmp.replace(p)


def update_kind(raw: dict[str, Any]) -> str:
    return (
        "callback_query"
        if raw.get("callback_query")
        else "message"
        if raw.get("message")
        else "other"
    )


class Poller:
    def __init__(
        self,
        client: HttpTelegramClient,
        stop: threading.Event,
        handler: Callable[[dict[str, Any]], tuple[int, dict[str, Any]]] | None = None,
        sleep: Callable[[float], Any] | None = None,
    ) -> None:
        self.client = client
        self.stop = stop
        self.handler = handler or self._default_handler
        self._sleep = sleep or self._stoppable_sleep
        self.offset = load_offset()

    @staticmethod
    def _default_handler(raw: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return handle_local_poll(raw, build_deps())

    async def _stoppable_sleep(self, seconds: float) -> None:
        end = asyncio.get_event_loop().time() + seconds
        while not self.stop.is_set() and asyncio.get_event_loop().time() < end:
            await asyncio.sleep(0.1)

    async def start(self) -> None:
        await self.client.delete_webhook(drop_pending_updates=False)
        log.info("tg poll started", offset=self.offset)

    async def process(self, raw: dict[str, Any]) -> None:
        uid = raw.get("update_id")
        log.info("tg update", update_id=uid, type=update_kind(raw))
        try:
            _, reply = await asyncio.to_thread(self.handler, raw)
            if reply.get("method"):
                await self.client.apply_reply(reply)
        except TgRetryAfter as exc:
            await self._sleep(exc.seconds)
        except TgError as exc:
            log.warning("tg reply failed", update_id=uid, error=type(exc).__name__)
        except Exception as exc:  # same as the webhook: never loop on one bad update
            log.warning("tg handler error", update_id=uid, error=type(exc).__name__)
        if isinstance(uid, int):
            self.offset = uid + 1
            save_offset(self.offset)

    async def step(self) -> int:
        """One getUpdates round. Returns the number of updates handled."""
        updates = await self.client.get_updates(self.offset, LONG_POLL_S)
        for raw in updates:
            await self.process(raw)
            if self.stop.is_set():
                break
        return len(updates)

    async def run(self) -> None:
        await self.start()
        delay = 1.0
        while not self.stop.is_set():
            try:
                await self.step()
                delay = 1.0
            except TgAuthError:
                log.error("tg poll stopped: bot token rejected")
                return
            except TgRetryAfter as exc:
                log.warning("tg rate limited", retry_after=exc.seconds)
                await self._sleep(exc.seconds)
            except TgConflict:
                log.warning(
                    "tg conflict 409: webhook or second consumer; removing webhook, retrying"
                )
                await self._sleep(delay)
                delay = min(delay * 2, BACKOFF_MAX)
                try:
                    await self.client.delete_webhook(drop_pending_updates=False)
                except TgError:
                    pass
            except TgError as exc:
                log.warning("tg poll error", error=type(exc).__name__, wait=delay)
                await self._sleep(delay)
                delay = min(delay * 2, BACKOFF_MAX)
        log.info("tg poll stopped", offset=self.offset)


def install_signals(stop: threading.Event) -> None:
    if threading.current_thread() is not threading.main_thread():
        return
    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is not None:
            signal.signal(sig, lambda *_: stop.set())


def main() -> None:
    load_dotenv()
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    stop = threading.Event()
    install_signals(stop)
    try:
        asyncio.run(Poller(HttpTelegramClient(), stop).run())
    except TgError as exc:
        print("FAILED:", type(exc).__name__, str(exc))  # messages never contain the token
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
