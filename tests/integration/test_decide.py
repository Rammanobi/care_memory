"""cm.review.decide: the single decision path."""

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest

from cm.contracts.review import ReviewDecisionIn, ReviewDecisionOut
from cm.core.db import transaction
from cm.review.decide import DecisionError, decide

pytestmark = pytest.mark.db
Make = Callable[..., UUID]


def _rows(sql: str, *args: Any) -> list[dict[str, Any]]:
    with transaction() as conn:
        return conn.execute(sql, args).fetchall()


def _decide(aid: UUID, actors: dict[str, Any], **kw: Any) -> ReviewDecisionOut:
    return decide(aid, ReviewDecisionIn(**kw), via="console", actor_id=actors["doctor"])


def test_approve_writes_decision_audit_and_outbox(
    make_approval: Make, actors: dict[str, Any]
) -> None:
    aid = make_approval()
    out = _decide(aid, actors, action="approve")
    assert out.status == "approved" and len(out.outbox_ids) == 1
    assert (
        _rows("SELECT status FROM cm.approvals WHERE approval_id=%s", aid)[0]["status"]
        == "approved"
    )
    d = _rows("SELECT * FROM cm.review_decisions WHERE approval_id=%s", aid)
    assert len(d) == 1 and d[0]["via"] == "console" and d[0]["doctor_id"] == actors["doctor"]
    ob = _rows("SELECT * FROM cm.outbox WHERE approval_id=%s", aid)
    assert (
        len(ob) == 1
        and ob[0]["decision_id"] == d[0]["decision_id"]
        and ob[0]["status"] == "pending"
    )
    assert ob[0]["recipient_id"] == actors["patient_person"]
    audit = _rows(
        "SELECT 1 FROM cm.audit_log WHERE action='decision.approve' AND thread_id="
        "(SELECT thread_id FROM cm.approvals WHERE approval_id=%s)",
        aid,
    )
    assert audit


def test_edit_sends_the_edited_text(make_approval: Make, actors: dict[str, Any]) -> None:
    aid = make_approval()
    out = _decide(aid, actors, action="edit", edited={"body": "Come on Saturday instead."})
    assert out.status == "edited"
    assert (
        _rows("SELECT body FROM cm.outbox WHERE approval_id=%s", aid)[0]["body"]
        == "Come on Saturday instead."
    )
    pl = _rows("SELECT payload FROM cm.approvals WHERE approval_id=%s", aid)[0]["payload"]
    assert pl["body"] == "Come on Saturday instead." and pl["original_body"].startswith(
        "Please come"
    )


def test_reject_sends_nothing_and_needs_reason_on_amber(
    make_approval: Make, actors: dict[str, Any]
) -> None:
    aid = make_approval(tier="amber")
    with pytest.raises(DecisionError) as exc:
        _decide(aid, actors, action="reject")
    assert exc.value.code == "reason_required"
    out = _decide(aid, actors, action="reject", reason="Not needed")
    assert out.status == "rejected" and out.outbox_ids == []
    assert _rows("SELECT 1 FROM cm.outbox WHERE approval_id=%s", aid) == []


def test_double_click_is_idempotent_and_conflict_is_409(
    make_approval: Make, actors: dict[str, Any]
) -> None:
    aid = make_approval()
    first = _decide(aid, actors, action="approve")
    second = _decide(aid, actors, action="approve")
    assert first.decision_id == second.decision_id and first.outbox_ids == second.outbox_ids
    assert len(_rows("SELECT 1 FROM cm.review_decisions WHERE approval_id=%s", aid)) == 1
    assert len(_rows("SELECT 1 FROM cm.outbox WHERE approval_id=%s", aid)) == 1
    with pytest.raises(DecisionError) as exc:
        _decide(aid, actors, action="reject", reason="changed my mind")
    assert exc.value.code == "already_decided" and exc.value.status == 409


def test_banned_term_blocks_and_rolls_back(make_approval: Make, actors: dict[str, Any]) -> None:
    aid = make_approval()
    with pytest.raises(DecisionError) as exc:
        _decide(aid, actors, action="edit", edited={"body": "Your TB test is ready."})
    assert exc.value.code == "banned_term"
    assert (
        _rows("SELECT status FROM cm.approvals WHERE approval_id=%s", aid)[0]["status"] == "pending"
    )
    assert _rows("SELECT 1 FROM cm.review_decisions WHERE approval_id=%s", aid) == []


def test_approval_without_recipients_creates_no_outbox(
    make_approval: Make, actors: dict[str, Any]
) -> None:
    aid = make_approval(audience="doctor", recipients=False)
    out = _decide(aid, actors, action="approve")
    assert out.outbox_ids == []
    assert _rows("SELECT 1 FROM cm.outbox WHERE approval_id=%s", aid) == []


def test_unknown_approval_is_not_found(actors: dict[str, Any]) -> None:
    with pytest.raises(DecisionError) as exc:
        _decide(uuid4(), actors, action="approve")
    assert exc.value.code == "not_found"
