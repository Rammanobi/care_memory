"""Lane G: task dispatch (local queue) and worker routes (/tasks/*).

Local mode (TASKS_MODE=local): the in-process queue calls ``dispatch``; the routes need an admin login.
Cloud mode: Cloud Tasks and Cloud Scheduler call the routes with a Google OIDC JWT. It is verified with
``cm.channels.gmail_oidc.verify_push_jwt`` (audience CM_TASKS_BASE_URL, email CM_TASKS_SA) and every
problem fails closed with 401. ``POST /tasks/run`` is what ``cm.core.tasks.enqueue`` targets: it claims the
``task_runs`` row (a replay of a finished task_id is acked without running), heartbeats while the handler
works, and answers 503 when SIGTERM arrived so the queue retries on a fresh instance.
"""
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

import contextlib
import re
import threading
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from cm.api.deps import ApiError, current_user, require_roles
from cm.channels import gmail_oidc
from cm.core import lifecycle
from cm.core import tasks as core_tasks
from cm.core.logging import get_logger
from cm.core.retry import classify

router = APIRouter(prefix="/tasks", tags=["tasks"])
log = get_logger()

HEARTBEAT_EVERY_S = 20.0
_TASK_ID = re.compile(r"^[A-Za-z0-9_-]{1,500}$")
_TASK_TYPE = {
    "drain_outbox": "drain_outbox",
    "checkins": "checkins",
    "nightly": "nightly",
    "calendar_sync": "calendar_sync",
    "tap": "ingest_event",
    "ingest_event": "ingest_event",
}
_key_fetcher: gmail_oidc.KeyFetcher | None = None


def set_key_fetcher(fn: gmail_oidc.KeyFetcher | None) -> None:
    """Inject the public-key fetcher (tests). ``None`` restores Google's cert endpoint (cached)."""
    global _key_fetcher
    _key_fetcher = fn


def _fetcher() -> gmail_oidc.KeyFetcher:
    global _key_fetcher
    if _key_fetcher is None:
        _key_fetcher = gmail_oidc.google_cert_fetcher()
    return _key_fetcher


def dispatch(queue: str, name: str, payload: Any) -> None:
    """Run one queued task. Intake of taps and free text beyond the saved event is not wired yet."""
    kind = payload.get("kind") if isinstance(payload, dict) else None
    if kind == "drain_outbox":
        from cm.jobs.outbox_drainer import drain_once

        drain_once()
    elif kind == "checkins":
        from cm.jobs.reminders import produce

        produce()
    elif kind == "nightly":
        from cm.jobs.nightly import run_patient

        run_patient(str(payload["patient"]), live=bool(payload.get("live", False)))
    elif kind == "calendar_sync":
        log.info("calendar_sync is a stub", queue=queue)  # Lane M wires the real sync
    elif kind in ("tap", "ingest_event"):
        # The event row is saved before enqueue; the memory pipeline picks it up (not wired here yet).
        log.info("task acked", queue=queue, kind=kind)
    else:
        log.info("task has no handler yet", queue=queue, kind=kind)


def _verify_oidc(request: Request) -> dict[str, Any]:
    try:
        token = gmail_oidc.bearer_token(request.headers.get("authorization"))
        return gmail_oidc.verify_push_jwt(
            token,
            audience=_cfg(core_tasks.tasks_base_url),
            expected_email=_cfg(core_tasks.tasks_service_account),
            key_fetcher=_fetcher(),
        )
    except gmail_oidc.PushAuthError as exc:
        log.warning("tasks auth refused", reason=exc.reason)
        raise ApiError(401, "Task caller not authenticated", "unauthenticated") from exc


def _cfg(getter: Any) -> str:
    try:
        return str(getter())
    except core_tasks.TasksConfigError:
        return ""  # verify_push_jwt turns an empty audience/email into not_configured: fail closed


def _guard(request: Request) -> Any:
    """Cloud mode: Google OIDC from Cloud Tasks or Scheduler. Local mode: admin login."""
    if core_tasks.mode() == "cloud":
        return _verify_oidc(request)
    return require_roles("admin")(current_user(request))


@contextlib.contextmanager
def _heartbeating(task_id: str) -> Iterator[None]:
    from cm.store import task_runs_repo

    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(HEARTBEAT_EVERY_S):
            try:
                task_runs_repo.heartbeat(task_id)
            except Exception as exc:  # noqa: BLE001  (a missed beat must not kill the handler)
                log.warning("heartbeat failed", error=type(exc).__name__)

    t = threading.Thread(target=beat, name="cm-task-heartbeat", daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join(timeout=2)


class RunIn(BaseModel):
    queue: str = "agent-runs"
    task_id: str | None = None
    payload: Any = None


@router.post("/run")
def run(body: RunIn, request: Request, _: Any = Depends(_guard)) -> dict[str, Any]:
    """Target of the Cloud Tasks HTTP task. Idempotent per task_id."""
    from cm.store import task_runs_repo

    task_id = request.headers.get("x-cloudtasks-taskname") or body.task_id or ""
    if not _TASK_ID.match(task_id):
        raise ApiError(400, "Missing or invalid task_id", "invalid_task_id")
    kind = body.payload.get("kind") if isinstance(body.payload, dict) else None
    task_type = _TASK_TYPE.get(str(kind))
    if task_type is None:
        log.info("task has no handler yet", queue=body.queue, kind=kind)
        return {"status": "no_handler", "task_id": task_id}
    if lifecycle.shutting_down():
        raise ApiError(503, "Shutting down; retry", "shutting_down")
    got = task_runs_repo.claim(task_id, task_type)
    if got.status == "done":
        return {"status": "duplicate", "task_id": task_id}
    if got.status == "busy":
        raise ApiError(409, "Task is running elsewhere", "in_progress")
    try:
        with _heartbeating(task_id):
            dispatch(body.queue, task_id, body.payload)
    except Exception as exc:  # noqa: BLE001
        cls = classify(exc).error_class
        task_runs_repo.finish(task_id, ok=False, error=type(exc).__name__, error_class=cls)
        log.warning("task failed", kind=kind, error=type(exc).__name__, error_class=cls)
        if cls in ("spend_cap", "auth", "invalid"):  # retrying cannot help: ack so the queue stops
            return {"status": "failed", "task_id": task_id, "error_class": cls}
        raise ApiError(500, "Task failed; retry", "task_failed") from exc
    task_runs_repo.finish(task_id, ok=True)
    return {"status": "ok", "task_id": task_id, "attempt": got.attempt}


@router.post("/drain-outbox")
def drain_outbox(_: Any = Depends(_guard)) -> dict[str, int]:
    """Idempotent: safe for Cloud Scheduler to call every minute (rows are claimed once)."""
    from cm.jobs.outbox_drainer import drain_once

    return drain_once()


@router.post("/checkins")
def checkins(_: Any = Depends(_guard)) -> dict[str, int]:
    from cm.jobs.reminders import produce

    return produce()


@router.post("/checkin-nudge")
def checkin_nudge(_: Any = Depends(_guard)) -> dict[str, str]:
    return {"status": "not_implemented"}
