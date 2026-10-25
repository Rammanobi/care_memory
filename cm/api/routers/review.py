"""Lane G: doctor gate routes. Every decision goes through cm.review.decide.decide (non-negotiable 14)."""
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from cm.api.deps import ApiError, User, now, parse_cursor, require_roles, resolve_patient
from cm.contracts.review import (
    BulkDecisionIn,
    DecisionRecord,
    EvidenceItem,
    ProposalOut,
    ReviewDecisionIn,
    ReviewDecisionOut,
    ReviewItem,
    ReviewItemDetail,
    ReviewQueueOut,
)
from cm.core import clock
from cm.core.db import transaction
from cm.review.decide import DecisionError, decide
from cm.store import approvals_repo

REQUEST_SUBKINDS = ("patient_request", "document_review")  # live on the Requests page, not the queue

router = APIRouter(prefix="/review", tags=["review"])
doctor_only = require_roles("doctor")
doctor_or_admin = require_roles("doctor", "admin")


def item_from_row(r: dict[str, Any]) -> ReviewItem:
    drivers = [EvidenceItem.model_validate(e) for e in r["evidence"][:3]]
    return ReviewItem(
        approval_id=r["approval_id"],
        patient_id=r["patient_id"],
        patient_token=r.get("patient_token"),
        thread_id=r["thread_id"],
        interrupt_id=r["interrupt_id"],
        task_id=r["task_id"],
        proposal_group_id=r["proposal_group_id"],
        graph_kind=r["graph_kind"],
        tier=r["tier"],
        kind=r["kind"],
        title=r["payload"].get("title", ""),
        status=r["status"],
        drivers=drivers,
        evidence_count=r.get("evidence_count") or len(r["evidence"]),
        created_at=r["created_at"],
        due_at=r["due_at"],
        expires_at=r["expires_at"],
        reminded_at=r["reminded_at"],
        escalated_at=r["escalated_at"],
        redraft_count=r["redraft_count"],
        sample_reason=r["sample_reason"],
        delivery=r.get("delivery") or "none",
    )


def decision_to_http(exc: DecisionError) -> ApiError:
    return ApiError(exc.status, exc.code.replace("_", " ").capitalize(), exc.code, exc.detail)


@router.get("/queue", response_model=ReviewQueueOut)
def review_queue(
    tier: str | None = None,
    status: str | None = "pending",
    kind: str | None = None,
    patient_id: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    _: User = Depends(doctor_or_admin),
) -> ReviewQueueOut:
    at = now()
    limit = max(1, min(limit, 200))
    offset = parse_cursor(cursor)
    with transaction() as conn:
        pid = resolve_patient(conn, patient_id)["patient_id"] if patient_id else None
        rows = approvals_repo.queue(
            at,
            status=status,
            tier=tier,
            kind=kind,
            patient_id=pid,
            exclude_subkind=REQUEST_SUBKINDS,
            cursor=offset,
            limit=limit + 1,
            conn=conn,
        )
        tiers = approvals_repo.count_pending_by_tier(at, conn=conn)
        extra = conn.execute(
            "SELECT count(*) FILTER (WHERE due_at < %s) AS overdue, count(*) FILTER (WHERE escalated_at IS NOT NULL) AS esc "
            "FROM cm.approvals WHERE status='pending' AND COALESCE(payload->>'subkind','') NOT IN ('patient_request','document_review')",
            (at,),
        ).fetchone()
        sim_day = clock.current_sim_day(conn)
    more = len(rows) > limit
    counts = {
        "red": tiers.get("red", 0),
        "amber": tiers.get("amber", 0),
        "green": tiers.get("green", 0),
        "overdue": extra["overdue"],
        "escalated": extra["esc"],
    }
    return ReviewQueueOut(
        counts=counts,
        items=[item_from_row(r) for r in rows[:limit]],
        next_cursor=str(offset + limit) if more else None,
        server_time=at,
        sim_day=sim_day,
    )


@router.get("/{approval_id}", response_model=ReviewItemDetail)
def review_detail(approval_id: UUID, _: User = Depends(doctor_or_admin)) -> ReviewItemDetail:
    at = now()
    with transaction() as conn:
        r = approvals_repo.get(approval_id, at, conn=conn)
        if not r:
            raise ApiError(404, "Approval not found", "not_found")
        hist = conn.execute(
            "SELECT d.*, p.token FROM cm.review_decisions d LEFT JOIN cm.persons p ON p.person_id=d.doctor_id "
            "WHERE d.approval_id=%s",
            (approval_id,),
        ).fetchall()
    base = item_from_row(r)
    ev = [EvidenceItem.model_validate(e) for e in r["evidence"]]
    pf = ProposalOut.model_fields
    return ReviewItemDetail(
        **base.model_dump(),
        proposal=ProposalOut.model_validate({k: v for k, v in r["payload"].items() if k in pf}),
        evidence=ev,
        citations=[e.citation for e in ev],
        history=[
            DecisionRecord(
                decision_id=h["decision_id"],
                action=h["action"],
                doctor_token=h["token"],
                via=h["via"],
                decided_at=h["decided_at"],
                reason=h["reason"],
            )
            for h in hist
        ],
    )


class BulkItemResult(ReviewDecisionOut):
    """ReviewDecisionOut plus ok and message; error_code is open (any decide() code) in a bulk run."""

    ok: bool = True
    message: str | None = None
    error_code: str | None = None  # type: ignore[assignment]


_BULK_MESSAGES = {
    "not_found": "Approval not found",
    "red_not_bulk": "Red items must be decided one at a time",
    "amber_not_viewed": "Open this Amber item before approving it",
    "already_decided": "Already decided",
    "banned_term": "The draft contains a word that cannot be sent to a patient",
    "reason_required": "A reason is required",
}


@router.post("/bulk-decision", response_model=list[BulkItemResult])
def bulk_decision(body: BulkDecisionIn, user: User = Depends(doctor_only)) -> list[BulkItemResult]:
    """HTTP 200 even on partial success; read each item's ok / error_code / message."""
    out: list[BulkItemResult] = []
    for aid in body.approval_ids:
        with transaction() as conn:
            row = approvals_repo.get(aid, now(), conn=conn)
        if not row:
            out.append(_err(aid, "not_found"))
        elif row["tier"] == "red":
            out.append(_err(aid, "red_not_bulk"))
        elif row["tier"] == "amber" and aid not in body.viewed_approval_ids:
            out.append(_err(aid, "amber_not_viewed"))
        else:
            try:
                res = decide(
                    aid,
                    ReviewDecisionIn(action="approve", evidence_viewed=True),
                    via="console",
                    actor_id=user.person_id,
                )
                out.append(BulkItemResult(**res.model_dump(exclude={"error_code"}), ok=True))
            except DecisionError as exc:
                out.append(_err(aid, exc.code, exc.detail))
    return out


def _err(aid: UUID, code: str, detail: str | None = None) -> BulkItemResult:
    return BulkItemResult(
        approval_id=aid,
        action="approve",
        status="pending",
        via="console",
        ok=False,
        error_code=code,
        message=_BULK_MESSAGES.get(code) or detail or code.replace("_", " ").capitalize(),
    )


@router.post("/{approval_id}/decision", response_model=ReviewDecisionOut)
def post_decision(
    approval_id: UUID, body: ReviewDecisionIn, user: User = Depends(doctor_only)
) -> ReviewDecisionOut:
    try:
        return decide(approval_id, body, via="console", actor_id=user.person_id)
    except DecisionError as exc:
        raise decision_to_http(exc) from exc
