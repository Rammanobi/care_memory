"""Lane G: patient requests (UI "requests" tab). A request is an approvals row with subkind
'patient_request': the patient's text lives in payload.data, the assistant's draft reply in payload.body.
The decision goes through cm.review.decide.decide like every other approval."""
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from cm.api import readmodels as rm
from cm.api.deps import ApiError, User, now, require_roles
from cm.api.portal_models import RequestOut, RequestStatus
from cm.api.routers.review import decision_to_http
from cm.contracts.review import ReviewDecisionIn, ReviewDecisionOut
from cm.core.db import transaction
from cm.review.decide import DecisionError, decide

router = APIRouter(prefix="/requests", tags=["requests"])


@router.get("", response_model=list[RequestOut])
def list_requests(
    status: RequestStatus | None = None,
    code: str | None = None,
    _: User = Depends(require_roles("doctor", "admin")),
) -> list[RequestOut]:
    with transaction() as conn:
        return rm.request_rows(conn, now(), code=code, status=status)


@router.get("/{request_id}", response_model=RequestOut)
def get_request(
    request_id: UUID, _: User = Depends(require_roles("doctor", "admin"))
) -> RequestOut:
    with transaction() as conn:
        rows = [r for r in rm.request_rows(conn, now()) if r.id == request_id]
    if not rows:
        raise ApiError(404, "Request not found", "not_found")
    return rows[0]


@router.post("/{request_id}/decision", response_model=ReviewDecisionOut)
def decide_request(
    request_id: UUID, body: ReviewDecisionIn, user: User = Depends(require_roles("doctor"))
) -> ReviewDecisionOut:
    try:
        return decide(request_id, body, via="console", actor_id=user.person_id)
    except DecisionError as exc:
        raise decision_to_http(exc) from exc
