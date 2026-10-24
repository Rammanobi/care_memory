"""Lane A: task enqueue. ``TASKS_MODE=local`` runs an in-process queue (dev only); ``cloud`` is a stub.

A task is identified by ``name`` (colon-free). Enqueueing the same name twice is a no-op, which mirrors
Cloud Tasks task-name dedup. The local worker thread is started by the API at startup, only in dev.
"""

from __future__ import annotations

import os
import queue as _q
import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from cm.core.logging import get_logger

log = get_logger()

Dispatcher = Callable[[str, str, Any], None]

_queue: _q.Queue[tuple[str, str, Any]] = _q.Queue()
_seen: OrderedDict[str, None] = OrderedDict()
_lock = threading.Lock()
_worker: threading.Thread | None = None
_stop = threading.Event()
_dispatcher: Dispatcher | None = None
_SEEN_MAX = 5000


def mode() -> str:
    return os.environ.get("TASKS_MODE", "local").strip().lower()


def enqueue(queue: str, name: str, payload: Any) -> None:
    """Enqueue a named task. Repeating a name is a no-op."""
    if mode() == "cloud":
        raise NotImplementedError(
            "TASKS_MODE=cloud: Cloud Tasks enqueue is not wired in this build; set TASKS_MODE=local"
        )
    with _lock:
        if name in _seen:
            return
        _seen[name] = None
        while len(_seen) > _SEEN_MAX:
            _seen.popitem(last=False)
    _queue.put((queue, name, payload))


def set_dispatcher(fn: Dispatcher | None) -> None:
    global _dispatcher
    _dispatcher = fn


def _dispatch(queue: str, name: str, payload: Any) -> None:
    fn = _dispatcher
    if fn is None:
        from cm.api.routers.tasks import dispatch  # late import: avoids a cycle at module load

        fn = dispatch
    try:
        fn(queue, name, payload)
    except Exception as exc:  # a failed task never kills the worker; the name stays consumed
        log.warning("local task failed", queue=queue, error=type(exc).__name__)


def run_pending(limit: int = 1000) -> int:
    """Run queued tasks on the calling thread (tests, scripts). Returns how many ran."""
    n = 0
    while n < limit:
        try:
            item = _queue.get_nowait()
        except _q.Empty:
            break
        _dispatch(*item)
        n += 1
    return n


def pending() -> int:
    return _queue.qsize()


def _loop() -> None:
    while not _stop.is_set():
        try:
            item = _queue.get(timeout=0.5)
        except _q.Empty:
            continue
        _dispatch(*item)


def start_local_worker() -> bool:
    """Start the dev worker thread. Returns False when not in local mode or already running."""
    global _worker
    if mode() != "local" or (_worker is not None and _worker.is_alive()):
        return False
    _stop.clear()
    _worker = threading.Thread(target=_loop, name="cm-local-tasks", daemon=True)
    _worker.start()
    return True


def stop_local_worker() -> None:
    global _worker
    _stop.set()
    if _worker is not None:
        _worker.join(timeout=2)
    _worker = None


def reset_for_tests() -> None:
    with _lock:
        _seen.clear()
    while True:
        try:
            _queue.get_nowait()
        except _q.Empty:
            break
