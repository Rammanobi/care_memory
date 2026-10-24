"""Integration: outbox drainer. Claims due Telegram rows (SKIP LOCKED), sends each through
``tg_sender.send_outbox`` and acts on the SendResult.

Dev loop:  python -m cm.jobs.outbox_drainer [--once] [--interval 5]
Worker route /tasks/drain-outbox calls ``drain_once``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import time
from datetime import timedelta
from typing import Any

from cm.channels.adapters_pg import (
    PgAudit,
    PgBindings,
    PgConsents,
    PgEvents,
    PgOutbox,
    PgTasks,
    shared_limiter,
)
from cm.channels.ports import TelegramClient
from cm.channels.tg_sender import SenderDeps, send_outbox
from cm.core import clock
from cm.core.logging import get_logger
from cm.store import outbox_repo

log = get_logger()
MAX_ATTEMPTS = 8
WORKER = f"drainer-{socket.gethostname()}-{os.getpid()}"


def batch_size() -> int:
    return int(os.environ.get("DRAIN_BATCH", "20"))


def make_deps(client: TelegramClient | None = None) -> SenderDeps:
    if client is None:
        from cm.channels.tg_http import HttpTelegramClient

        client = HttpTelegramClient()
    return SenderDeps(
        client=client,
        outbox=PgOutbox(),
        bindings=PgBindings(),
        consents=PgConsents(),
        events=PgEvents(),
        tasks=PgTasks(),
        audit=PgAudit(),
        limiter=shared_limiter(),
        now=clock.now,
    )


def _settle(row: dict[str, Any], res: Any, count: dict[str, int]) -> None:
    """Make sure a claimed row does not stay 'sending'."""
    cur = outbox_repo.get(row["outbox_id"])
    if cur is None or cur["status"] != "sending":
        return
    at = clock.now()
    if res.status == "retry" and row["attempts"] < MAX_ATTEMPTS:
        wait = timedelta(seconds=max(float(res.retry_after_s or 30), 1.0))
        outbox_repo.mark(row["outbox_id"], "pending", next_attempt_at=at + wait)
    elif res.status == "skipped":
        outbox_repo.mark(row["outbox_id"], "failed", error=f"skipped:{res.skip_reason}")
    else:
        outbox_repo.mark(row["outbox_id"], "failed", error=res.error or res.skip_reason or "failed")


async def _run(rows: list[dict[str, Any]], deps: SenderDeps) -> dict[str, int]:
    count = {"claimed": len(rows), "sent": 0, "retry": 0, "failed": 0, "skipped": 0}
    for row in rows:
        try:
            res = await send_outbox(row, deps)
        except Exception as exc:  # one bad row must not stop the batch
            log.warning("send crashed", error=type(exc).__name__)
            outbox_repo.mark(row["outbox_id"], "pending", next_attempt_at=clock.now() + timedelta(seconds=60))
            count["retry"] += 1
            continue
        count[res.status] = count.get(res.status, 0) + 1
        _settle(row, res, count)
    return count


def drain_once(client: TelegramClient | None = None, limit: int | None = None) -> dict[str, int]:
    rows = outbox_repo.claim_for_send(limit or batch_size(), WORKER, clock.now())
    if not rows:
        return {"claimed": 0, "sent": 0, "retry": 0, "failed": 0, "skipped": 0}
    return asyncio.run(_run(rows, make_deps(client)))


def main() -> None:
    ap = argparse.ArgumentParser(description="Drain the Telegram outbox")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=5.0)
    a = ap.parse_args()
    while True:
        out = drain_once()
        if out["claimed"]:
            log.info("drained", **out)
        if a.once:
            print(out)
            return
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
