"""Lane A: task enqueue. ``TASKS_MODE=local`` runs an in-process queue (dev only); ``cloud`` creates
Cloud Tasks HTTP tasks.

A task is identified by ``name`` = task_id (colon-free). Enqueueing the same name twice is a no-op, which
mirrors Cloud Tasks task-name dedup (ALREADY_EXISTS is treated as success). The local worker thread is
started by the API at startup, only in dev.

Cloud mode env (names only): CM_TASKS_BASE_URL (target and OIDC audience), CM_TASKS_SA (OIDC service
account), CM_TASKS_QUEUE_AGENT_RUNS / _RESUMES / _OUTBOUND (queue names; fall back to TASKS_QUEUE_*),
GCP_PROJECT, GCP_REGION. The google-cloud-tasks client is imported lazily and can be injected.
"""

from __future__ import annotations

import json
import os
import queue as _q
import re
import threading
from collections import OrderedDict
from collections.abc import Callable
from datetime import timedelta
from typing import Any, Protocol

from cm.core import clock
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


class TasksConfigError(RuntimeError):
    """Cloud mode is selected but a required env var is missing (message names the variable only)."""


class CloudTasksClient(Protocol):
    """The slice of ``google.cloud.tasks_v2.CloudTasksClient`` we use."""

    def create_task(self, request: dict[str, Any]) -> Any: ...


_cloud_client: CloudTasksClient | None = None
_TASK_ID = re.compile(r"^[A-Za-z0-9_-]{1,500}$")
_QUEUE_ENV = {
    "agent-runs": ("CM_TASKS_QUEUE_AGENT_RUNS", "TASKS_QUEUE_AGENT_RUNS"),
    "resumes": ("CM_TASKS_QUEUE_RESUMES", "TASKS_QUEUE_RESUMES"),
    "outbound": ("CM_TASKS_QUEUE_OUTBOUND", "TASKS_QUEUE_OUTBOUND"),
}


def set_cloud_client(client: CloudTasksClient | None) -> None:
    """Inject a client (tests). ``None`` goes back to the lazily built real client."""
    global _cloud_client
    _cloud_client = client


def _env(*names: str) -> str:
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    raise TasksConfigError(f"{names[0]} is not set")


def tasks_base_url() -> str:
    return _env("CM_TASKS_BASE_URL").rstrip("/")


def tasks_service_account() -> str:
    return _env("CM_TASKS_SA", "TASKS_INVOKER_SA")


def _get_client() -> CloudTasksClient:
    global _cloud_client
    if _cloud_client is None:
        try:
            from google.cloud import tasks_v2  # lazy: only cloud mode needs the package
        except ImportError as exc:
            raise TasksConfigError("google-cloud-tasks is not installed") from exc
        _cloud_client = tasks_v2.CloudTasksClient()
    return _cloud_client


def _is_already_exists(exc: Exception) -> bool:
    return type(exc).__name__ == "AlreadyExists" or getattr(exc, "code", None) in (
        409,
        "ALREADY_EXISTS",
    )


def _queue_path(queue: str) -> str:
    envs = _QUEUE_ENV.get(queue)
    qname = _env(*envs) if envs and any(os.environ.get(e) for e in envs) else queue
    return f"projects/{_env('GCP_PROJECT')}/locations/{_env('GCP_REGION')}/queues/{qname}"


def _enqueue_cloud(queue: str, name: str, payload: Any, delay_s: float) -> None:
    if not _TASK_ID.match(name):
        raise ValueError("task_id must be 1-500 chars of letters, digits, hyphen or underscore")
    base, sa = tasks_base_url(), tasks_service_account()
    parent = _queue_path(queue)
    body = json.dumps({"queue": queue, "task_id": name, "payload": payload}, default=str).encode()
    task: dict[str, Any] = {
        "name": f"{parent}/tasks/{name}",
        "http_request": {
            "http_method": "POST",
            "url": f"{base}/tasks/run",
            "headers": {"Content-Type": "application/json"},
            "body": body,
            "oidc_token": {"service_account_email": sa, "audience": base},
        },
    }
    if delay_s > 0:
        task["schedule_time"] = clock.now() + timedelta(seconds=delay_s)
    try:
        _get_client().create_task(request={"parent": parent, "task": task})
    except Exception as exc:  # noqa: BLE001
        if _is_already_exists(exc):
            return  # same task_id already queued or recently ran: idempotent success
        raise


def enqueue(queue: str, name: str, payload: Any, *, delay_s: float = 0) -> None:
    """Enqueue a named task. Repeating a name is a no-op. ``delay_s`` schedules it later (cloud mode)."""
    if mode() == "cloud":
        _enqueue_cloud(queue, name, payload, delay_s)
        return
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
