"""Integration: one command to make the Telegram bot live on a laptop.

    python -m cm.jobs.dev_telegram [--interval 5]

Runs the long-poll receiver (cm.jobs.tg_poll) and the outbox drainer loop together. Ctrl+C or SIGTERM stops both.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import threading

from cm.channels.tg_http import HttpTelegramClient
from cm.core.config import load_dotenv
from cm.core.logging import get_logger
from cm.jobs import outbox_drainer
from cm.jobs.tg_poll import Poller, install_signals

log = get_logger()


def drain_loop(stop: threading.Event, interval: float) -> None:
    while not stop.is_set():
        try:
            out = outbox_drainer.drain_once()
            if out["claimed"]:
                log.info("drained", **out)
        except Exception as exc:  # keep the loop alive
            log.warning("drain error", error=type(exc).__name__)
        stop.wait(interval)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=5.0)
    a = ap.parse_args()
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    stop = threading.Event()
    install_signals(stop)
    t = threading.Thread(target=drain_loop, args=(stop, a.interval), daemon=True)
    t.start()
    try:
        asyncio.run(Poller(HttpTelegramClient(), stop).run())
    finally:
        stop.set()
        t.join(timeout=10)


if __name__ == "__main__":
    main()
