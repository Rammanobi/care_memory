"""SIGTERM flag and heartbeat interface (04_platform F4). Tiny on purpose."""

from __future__ import annotations

import signal
import threading
from typing import Protocol

_flag = threading.Event()


def shutting_down() -> bool:
    """True once SIGTERM arrived. Long handlers poll this (CLAUDE.md rule 13)."""
    return _flag.is_set()


def request_shutdown() -> None:
    _flag.set()


def reset() -> None:
    _flag.clear()


def install_sigterm_handler() -> None:
    signal.signal(signal.SIGTERM, lambda *_: request_shutdown())


class Heartbeat(Protocol):
    """Implemented by the task_runs store: touch heartbeat_at at least every 20 s."""

    def beat(self, task_id: str, attempt: int) -> None: ...
