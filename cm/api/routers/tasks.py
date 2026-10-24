"""Lane G: task dispatch (local queue) and worker routes (/tasks/*).

Local mode (TASKS_MODE=local): the in-process queue calls ``dispatch``; the routes need an admin
login. Cloud mode (OIDC from Cloud Tasks / Scheduler) is not wired yet and answers 501.
"""
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from cm.api.deps import ApiError, User, require_roles
from cm.core import tasks as core_tasks
from cm.core.logging import get_logger

router = APIRouter(prefix="/tasks", tags=["tasks"])
log = get_logger()


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
    else:
        log.info("task has no handler yet", queue=queue, kind=kind)


def _guard(user: User = Depends(require_roles("admin"))) -> User:
    if core_tasks.mode() == "cloud":
        raise ApiError(501, "Cloud Tasks auth not wired", "not_implemented")
    return user


@router.post("/drain-outbox")
def drain_outbox(_: User = Depends(_guard)) -> dict[str, int]:
    from cm.jobs.outbox_drainer import drain_once

    return drain_once()


@router.post("/checkins")
def checkins(_: User = Depends(_guard)) -> dict[str, int]:
    from cm.jobs.reminders import produce

    return produce()


@router.post("/checkin-nudge")
def checkin_nudge(_: User = Depends(_guard)) -> dict[str, str]:
    return {"status": "not_implemented"}
