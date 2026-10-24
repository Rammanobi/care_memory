"""Lane A: task_runs claim / heartbeat / finish (INTEGRATION_DECISIONS §a2 T10 and Z2).

The row key is ``task_id`` (the Cloud Task name). ``claim`` makes delivery idempotent: a task that
already succeeded is reported ``done`` (the caller acks without running), one whose heartbeat is fresh is
``busy`` (the caller answers 409 so Cloud Tasks retries later), anything else is ``claimed`` and the
attempt counter goes up.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from typing import Literal

from cm.core import clock
from cm.core.db import transaction

STALE_AFTER_S = 60  # heartbeats come every <= 20 s; three missed beats means the worker died


@dataclass(frozen=True)
class Claim:
    status: Literal["claimed", "done", "busy"]
    attempt: int = 0


def _instance() -> str:
    return os.environ.get("K_REVISION") or socket.gethostname()


def claim(task_id: str, task_type: str) -> Claim:
    """Move a task to running. ``done`` if it already succeeded, ``busy`` if another worker is live."""
    now = clock.now()
    with transaction() as conn:
        row = conn.execute(
            "INSERT INTO cm.task_runs (task_id, task_type, state, attempt, heartbeat_at, worker_instance, "
            "created_at, updated_at) VALUES (%(t)s, %(ty)s, 'running', 1, %(now)s, %(w)s, %(now)s, %(now)s) "
            "ON CONFLICT (task_id) DO UPDATE SET state='running', attempt=cm.task_runs.attempt+1, "
            "heartbeat_at=%(now)s, worker_instance=%(w)s, error=NULL, error_class=NULL, updated_at=%(now)s "
            "WHERE cm.task_runs.state <> 'succeeded' AND NOT (cm.task_runs.state='running' "
            "AND cm.task_runs.heartbeat_at > %(now)s - make_interval(secs => %(stale)s)) "
            "RETURNING attempt",
            {"t": task_id, "ty": task_type, "now": now, "w": _instance(), "stale": STALE_AFTER_S},
        ).fetchone()
        if row:
            return Claim("claimed", int(row["attempt"]))
        cur = conn.execute("SELECT state FROM cm.task_runs WHERE task_id=%s", (task_id,)).fetchone()
    return Claim("done" if cur and cur["state"] == "succeeded" else "busy")


def heartbeat(task_id: str) -> None:
    """Touch heartbeat_at (call at least every 20 s from long handlers)."""
    now = clock.now()
    with transaction() as conn:
        conn.execute(
            "UPDATE cm.task_runs SET heartbeat_at=%s, updated_at=%s WHERE task_id=%s",
            (now, now, task_id),
        )


def finish(
    task_id: str, *, ok: bool, error: str | None = None, error_class: str | None = None
) -> None:
    now = clock.now()
    with transaction() as conn:
        conn.execute(
            "UPDATE cm.task_runs SET state=%s, error=%s, error_class=%s, updated_at=%s WHERE task_id=%s",
            (
                "succeeded" if ok else "failed",
                None if ok else (error or "")[:500],
                None if ok else error_class,
                now,
                task_id,
            ),
        )


def get_state(task_id: str) -> str | None:
    with transaction() as conn:
        row = conn.execute("SELECT state FROM cm.task_runs WHERE task_id=%s", (task_id,)).fetchone()
    return row["state"] if row else None
