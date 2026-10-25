"""Lane G: THE single doctor decision function (INTEGRATION_DECISIONS a3 K2, non-negotiable 14).

approve / edit / reject / expired in ONE transaction: the decision row, the approval status, the
ReviewDecisionEvent, the outbox rows and the audit entry. Idempotent per approval: repeating the same
action returns the first result and writes nothing; a different action is `already_decided`.
Outbox rows exist only here (the DB also refuses rows without approval_id + decision_id).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from psycopg.types.json import Jsonb

from cm.api.suppress import find_banned
from cm.contracts.review import ReviewDecisionIn, ReviewDecisionOut
from cm.core import clock
from cm.core.db import transaction
from cm.core.ids import idempotency_key
from cm.core.logging import get_logger
from cm.store import events_repo, outbox_repo

log = get_logger()
_STATUS = {"approve": "approved", "edit": "edited", "reject": "rejected", "expired": "expired"}
_OUTBOX_KIND = {
    "card": "card",
    "brief": "brief",
    "visit_list": "visit_list",
    "district_report": "district_report",
    "lab_confirm": "lab_confirm_notice",
}


class DecisionError(Exception):
    """Business-rule failure; `code` maps to api.Problem.code, `status` to the HTTP status."""

    def __init__(self, code: str, status: int, detail: str) -> None:
        super().__init__(detail)
        self.code, self.status, self.detail = code, status, detail


def _final_body(approval: dict[str, Any], d: ReviewDecisionIn) -> str | None:
    payload = approval["payload"]
    if d.action == "edit":
        body = (d.edited or {}).get("body")
        if not isinstance(body, str) or not body.strip():
            raise DecisionError("invalid_edit", 422, "edit needs edited.body")
        return body.strip()
    return payload.get("body")


def _validate(approval: dict[str, Any], d: ReviewDecisionIn, body: str | None) -> None:
    if (
        d.action == "reject"
        and approval["tier"] in ("red", "amber")
        and not (d.reason or "").strip()
    ):
        raise DecisionError(
            "reason_required", 422, "reason is required to reject a Red or Amber item"
        )
    if d.action in ("approve", "edit") and approval["payload"].get("audience") in (
        "patient",
        "supporter",
    ):
        hit = find_banned(body)
        if hit:
            raise DecisionError(
                "banned_term", 422, f"patient-facing text contains: {', '.join(hit)}"
            )


def _existing(conn: Any, approval_id: UUID, as_of: datetime) -> ReviewDecisionOut | None:
    row = conn.execute(
        "SELECT * FROM cm.review_decisions WHERE approval_id=%s", (approval_id,)
    ).fetchone()
    if not row:
        return None
    ids = [r["outbox_id"] for r in outbox_repo.for_approval(approval_id, as_of, conn=conn)]
    return ReviewDecisionOut(
        decision_id=row["decision_id"],
        approval_id=approval_id,
        action=row["action"],
        status=_STATUS[row["action"]],
        via=row["via"],
        decided_at=row["decided_at"],
        outbox_ids=ids,
    )


def _reply_meta(approval: dict[str, Any]) -> dict[str, Any]:
    """Threading info for a doctor's reply to a patient question (rows that carry data.origin only)."""
    payload = approval["payload"]
    data = payload.get("data") or {}
    origin = data.get("origin")
    if payload.get("subkind") != "patient_request" or not isinstance(origin, dict):
        return {}
    urgent = data.get("priority") == "urgent" or approval.get("tier") == "red"
    return {
        "reply_to": {
            "approval_id": str(approval["approval_id"]),
            "question_excerpt": origin.get("question_excerpt") or "",
            "telegram_message_id": origin.get("telegram_message_id"),
        },
        "patient_title": "Reply from your care team",
        "priority": "urgent" if urgent else "normal",
    }


def _outbox_meta(approval: dict[str, Any]) -> dict[str, Any]:
    payload = approval["payload"]
    data = payload.get("data") or {}
    keep = {k: data[k] for k in ("patient_title", "for_supporter") if k in data}
    return {"title": payload.get("title"), **keep, **_reply_meta(approval)}


def _write_outbox(
    conn: Any, approval: dict[str, Any], decision_id: UUID, body: str | None, at: datetime
) -> list[UUID]:
    ids: list[UUID] = []
    payload = approval["payload"]
    for r in payload.get("recipients", []):
        oid = outbox_repo.enqueue(
            {
                "kind": _OUTBOX_KIND.get(approval["kind"], "ai_message"),
                "recipient_id": r["person_id"],
                "channel": r["channel"],
                "body": body,
                "approval_id": approval["approval_id"],
                "decision_id": decision_id,
                "next_attempt_at": at,
                "for_date": payload.get("for_date"),
                "dedup_key": f"{decision_id}:{r['person_id']}:{r['channel']}:{payload.get('for_date') or 'now'}",
                "meta": _outbox_meta(approval),
            },
            conn=conn,
        )
        if oid:
            ids.append(oid)
    return ids


def _audit(
    conn: Any,
    approval: dict[str, Any],
    d: ReviewDecisionIn,
    actor_id: UUID | None,
    via: str,
    decision_id: UUID,
    outbox_ids: list[UUID],
    at: datetime,
) -> None:
    who = (
        conn.execute(
            "SELECT token, role FROM cm.persons WHERE person_id=%s", (actor_id,)
        ).fetchone()
        if actor_id
        else None
    )
    digest = hashlib.sha256(f"{approval['approval_id']}:{d.action}".encode()).hexdigest()
    conn.execute(
        "INSERT INTO cm.audit_log (at, actor, role, action, tool, args_hash, result_ids, patient_id, thread_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            at,
            who["token"] if who else "system",
            who["role"] if who else "system",
            f"decision.{d.action}",
            f"decide:{via}",
            digest,
            [str(decision_id), *map(str, outbox_ids)],
            approval["patient_id"],
            approval["thread_id"],
        ),
    )


def _decision_event(
    conn: Any,
    approval: dict[str, Any],
    d: ReviewDecisionIn,
    actor_id: UUID | None,
    decision_id: UUID,
    at: datetime,
) -> None:
    if not approval["patient_id"]:
        return
    events_repo.append_event(
        events_repo.NewEvent(
            patient_id=approval["patient_id"],
            type="ReviewDecisionEvent",
            occurred_at=at,
            recorded_at=at,
            source="console",
            reporter_id=actor_id,
            reporter_mode="record",
            payload={
                "approval_id": str(approval["approval_id"]),
                "decision_id": str(decision_id),
                "action": d.action,
                "kind": approval["kind"],
            },
            idempotency_key=idempotency_key("decision", str(approval["approval_id"])),
        ),
        conn=conn,
    )


def _after_commit(approval_id: UUID) -> None:
    """Post-decision follow-ups that must not share the decision transaction. Never raises."""
    try:
        from cm.uploads.review import on_decided

        on_decided(approval_id)  # no-op unless the approval is a document_review item
    except Exception as exc:  # noqa: BLE001  (a failed follow-up must not undo or hide the decision)
        log.warning("post-decision hook failed", error=type(exc).__name__)
        try:
            from cm.uploads.review import mark_index_failed

            mark_index_failed(approval_id, exc)  # state 'failed' + idempotent docidx-<id> retry task
        except Exception as exc2:  # noqa: BLE001
            log.warning("post-decision failure handling failed", error=type(exc2).__name__)


def decide(
    approval_id: UUID,
    d: ReviewDecisionIn,
    *,
    via: Literal["console", "gmail", "sweeper"],
    actor_id: UUID | None,
    conn: Any = None,
) -> ReviewDecisionOut:
    """Record a doctor decision atomically. Raises DecisionError on business-rule failures."""
    if conn is None:
        with transaction() as c:
            out = decide(approval_id, d, via=via, actor_id=actor_id, conn=c)
        _after_commit(approval_id)  # runs only once the decision is committed (idempotent hooks)
        return out
    at = clock.now()
    approval = conn.execute(
        "SELECT * FROM cm.approvals WHERE approval_id=%s FOR UPDATE", (approval_id,)
    ).fetchone()
    if not approval:
        raise DecisionError("not_found", 404, "approval not found")
    prior = _existing(conn, approval_id, at)
    if prior:
        if prior.action == d.action:
            return prior
        raise DecisionError("already_decided", 409, f"already {prior.status}")
    if approval["status"] != "pending":
        raise DecisionError("already_decided", 409, f"approval is {approval['status']}")
    body = _final_body(approval, d)
    _validate(approval, d, body)
    row = conn.execute(
        "INSERT INTO cm.review_decisions (approval_id, doctor_id, action, edited, reason, via, evidence_viewed, decided_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING decision_id",
        (
            approval_id,
            actor_id,
            d.action,
            Jsonb(d.edited) if d.edited else None,
            d.reason,
            via,
            d.evidence_viewed,
            at,
        ),
    ).fetchone()
    decision_id: UUID = row["decision_id"]
    payload = {**approval["payload"], "body": body} if d.action == "edit" else approval["payload"]
    if d.action == "edit":
        payload["original_body"] = approval["payload"].get("body")
    conn.execute(
        "UPDATE cm.approvals SET status=%s, payload=%s WHERE approval_id=%s",
        (_STATUS[d.action], Jsonb(payload), approval_id),
    )
    approval = {**approval, "payload": payload}
    ids = (
        _write_outbox(conn, approval, decision_id, body, at)
        if d.action in ("approve", "edit")
        else []
    )
    _audit(conn, approval, d, actor_id, via, decision_id, ids, at)
    _decision_event(conn, approval, d, actor_id, decision_id, at)
    return ReviewDecisionOut(
        decision_id=decision_id,
        approval_id=approval_id,
        action=d.action,
        status=_STATUS[d.action],
        via=via,
        decided_at=at,
        outbox_ids=ids,
    )
