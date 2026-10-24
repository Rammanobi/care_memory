"""Races on caremem_test: two doctors deciding the same item, N concurrent decide() calls (outbox
idempotency), double-tapped Telegram buttons, and two outbox drainers running at once."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from cm.channels.tg_client import FakeTelegramClient
from cm.contracts.review import ReviewDecisionIn
from cm.core import clock
from cm.core.db import transaction
from cm.jobs import outbox_drainer, reminders
from cm.memory.features import compute_features
from cm.review.decide import DecisionError, decide
from cm.store import approvals_repo, events_repo
from tests.integration.test_telegram_pg import bind, post, sent_reminder, tap

from .conftest import race

pytestmark = pytest.mark.db
Make = Callable[..., UUID]


def q(sql: str, *args: Any) -> list[dict[str, Any]]:
    with transaction() as conn:
        return conn.execute(sql, args).fetchall()


def _decide(aid: UUID, who: UUID, **kw: Any) -> Callable[[], Any]:
    return lambda: decide(aid, ReviewDecisionIn(**kw), via="console", actor_id=who)


def _side_effects(aid: UUID) -> dict[str, int]:
    return {
        "decisions": q("SELECT count(*) AS n FROM cm.review_decisions WHERE approval_id=%s", aid)[0]["n"],
        "outbox": q("SELECT count(*) AS n FROM cm.outbox WHERE approval_id=%s", aid)[0]["n"],
        "events": q(
            "SELECT count(*) AS n FROM cm.events WHERE type='ReviewDecisionEvent' AND payload->>'approval_id'=%s",
            str(aid),
        )[0]["n"],
        "audit": q(
            "SELECT count(*) AS n FROM cm.audit_log WHERE action LIKE 'decision.%%' AND thread_id="
            "(SELECT thread_id FROM cm.approvals WHERE approval_id=%s)",
            aid,
        )[0]["n"],
    }


# ----------------------------------------------------------------------------- decisions
def test_two_doctors_approve_the_same_item_at_once(
    make_approval: Make, actors: dict[str, Any], second_doctor: UUID
) -> None:
    aid = make_approval(tier="amber")
    a, b = race([_decide(aid, actors["doctor"], action="approve"),
                 _decide(aid, second_doctor, action="approve")])  # fmt: skip
    assert not isinstance(a, BaseException) and not isinstance(b, BaseException), (a, b)
    assert a.decision_id == b.decision_id and sorted(a.outbox_ids) == sorted(b.outbox_ids)
    assert _side_effects(aid) == {"decisions": 1, "outbox": 1, "events": 1, "audit": 1}


def test_approve_and_reject_race_has_one_winner(
    make_approval: Make, actors: dict[str, Any], second_doctor: UUID
) -> None:
    aid = make_approval(tier="amber")
    res = race([_decide(aid, actors["doctor"], action="approve"),
                _decide(aid, second_doctor, action="reject", reason="not needed")])  # fmt: skip
    wins = [r for r in res if not isinstance(r, BaseException)]
    losses = [r for r in res if isinstance(r, BaseException)]
    assert len(wins) == 1 and len(losses) == 1
    assert isinstance(losses[0], DecisionError) and losses[0].status == 409
    fx = _side_effects(aid)
    assert fx["decisions"] == 1 and fx["events"] == 1 and fx["audit"] == 1
    assert fx["outbox"] == (1 if wins[0].action == "approve" else 0)
    status = q("SELECT status FROM cm.approvals WHERE approval_id=%s", aid)[0]["status"]
    assert status == {"approve": "approved", "reject": "rejected"}[wins[0].action]


@pytest.mark.slow
def test_many_concurrent_decides_write_one_outbox_row(
    make_approval: Make, actors: dict[str, Any]
) -> None:
    aid = make_approval(tier="green")
    res = race([_decide(aid, actors["doctor"], action="approve") for _ in range(8)])
    assert all(not isinstance(r, BaseException) for r in res), res
    assert len({r.decision_id for r in res}) == 1
    assert _side_effects(aid) == {"decisions": 1, "outbox": 1, "events": 1, "audit": 1}
    keys = q("SELECT dedup_key FROM cm.outbox WHERE approval_id=%s", aid)
    assert len({k["dedup_key"] for k in keys}) == len(keys)


# ----------------------------------------------------------------------------- telegram taps
def test_same_update_delivered_concurrently_saves_one_event(env: dict[str, Any]) -> None:
    bind(env)
    oid, _ = sent_reminder(env)
    uid = uuid4().int % 10**9
    res = race([lambda: post(env, tap(f"c:{oid.hex}:t", uid)) for _ in range(6)])
    assert all(r[0] == 200 for r in res), res
    assert q("SELECT count(*) AS n FROM cm.events WHERE idempotency_key=%s", f"tg:{uid}")[0]["n"] == 1


def test_double_tap_taken_counts_the_day_once(env: dict[str, Any]) -> None:
    """Two taps on Taken (two Telegram updates) are two raw events, but the day is one taken dose."""
    bind(env)
    oid, _ = sent_reminder(env)
    u1, u2 = uuid4().int % 10**9, uuid4().int % 10**9
    res = race([lambda: post(env, tap(f"c:{oid.hex}:t", u1)), lambda: post(env, tap(f"c:{oid.hex}:t", u2))])
    assert all(r[0] == 200 for r in res), res
    rows = events_repo.query(env["patient"], clock.now() + timedelta(minutes=1), types=["DoseCheckin"])
    mine = [r for r in rows if r["payload"].get("prompt_outbox_id") == str(oid)]
    assert 1 <= len(mine) <= 2
    f = compute_features(rows, clock.now() + timedelta(minutes=1))
    days = {r["payload"]["for_date"] for r in mine}
    assert len(days) == 1 and f.checkins_total == len({r["payload"].get("for_date") for r in rows})
    assert f.taken_7d <= 7


def test_double_tap_missed_opens_one_red_draft(env: dict[str, Any]) -> None:
    bind(env)
    base = clock.now()
    for i, d in enumerate(("2026-02-28", "2026-03-01")):
        events_repo.append_event(events_repo.NewEvent(
            patient_id=env["patient"], type="DoseCheckin", occurred_at=base - timedelta(days=2 - i),
            recorded_at=base - timedelta(days=2 - i), source="system", idempotency_key=f"t-miss-{uuid4()}",
            payload={"status": "missed", "for_date": d},
        ))  # fmt: skip
    oid, _ = sent_reminder(env)
    taps = [uuid4().int % 10**9 for _ in range(4)]
    res = race([lambda u=u: post(env, tap(f"c:{oid.hex}:m", u)) for u in taps])
    assert all(r[0] == 200 for r in res), res
    red = q(
        "SELECT approval_id FROM cm.approvals WHERE patient_id=%s AND thread_id LIKE 'fast-missed_dose-%%' "
        "AND status='pending'",
        env["patient"],
    )
    assert len(red) == 1


# ----------------------------------------------------------------------------- drainer
def _approved_rows(env: dict[str, Any], doctor: UUID, n: int) -> list[UUID]:
    at = clock.now()
    out = []
    for i in range(n):
        rid = uuid4()
        aid = approvals_repo.upsert({
            "approval_id": rid, "patient_id": env["patient"], "thread_id": f"race-{rid}",
            "interrupt_id": "race", "tier": "green", "kind": "needs_human",
            "payload": {"audience": "patient", "title": f"Race {i}", "channel": "telegram",
                        "body": f"Please come to the clinic, note {i}.", "subkind": "outreach", "data": {},
                        "recipients": [{"person_id": str(env["person"]), "token": "P-9901",
                                        "channel": "telegram"}]},
            "created_at": at, "due_at": at + timedelta(hours=4), "expires_at": at + timedelta(hours=48),
        })  # fmt: skip
        out += decide(aid, ReviewDecisionIn(action="approve"), via="console", actor_id=doctor).outbox_ids
    return out


def test_two_drainers_send_each_row_at_most_once(env: dict[str, Any]) -> None:
    bind(env)
    assert reminders.produce()["created"] == 1
    doctor = q("SELECT person_id FROM cm.persons WHERE token='D-01'")[0]["person_id"]
    ids = _approved_rows(env, doctor, 3)
    mine = q("SELECT outbox_id FROM cm.outbox WHERE recipient_id=%s", env["person"])
    assert len(mine) == len(ids) + 1
    c1, c2 = FakeTelegramClient(), FakeTelegramClient()
    res = race([lambda: outbox_drainer.drain_once(c1), lambda: outbox_drainer.drain_once(c2)])
    assert all(not isinstance(r, BaseException) for r in res), res
    rows = q("SELECT status, provider_message_id FROM cm.outbox WHERE recipient_id=%s", env["person"])
    assert not [r for r in rows if r["status"] == "sending"], "a claimed row was left in 'sending'"
    to_me = [m for c in (c1, c2) for m in c.sent if str(m["chat_id"]) == "424242"]
    assert len(to_me) >= 1, rows
    assert len(to_me) == sum(r["status"] == "sent" for r in rows)
    assert len({m["text"] for m in to_me}) == len(to_me), "the same message went out twice"
    again = outbox_drainer.drain_once(FakeTelegramClient())  # a third run finds nothing new for us
    assert q("SELECT count(*) AS n FROM cm.outbox WHERE recipient_id=%s AND status='sending'",
             env["person"])[0]["n"] == 0 and again is not None  # fmt: skip
