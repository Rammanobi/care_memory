"""DB invariants on caremem_test: the outbox doctor gate, append-only tables, patient isolation and
as_of reads. Every statement runs on a connection that is rolled back afterwards."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from cm.store import approvals_repo, events_repo, outbox_repo

from .conftest import expect_db_error

pytestmark = pytest.mark.db
T = datetime(2026, 1, 20, 12, tzinfo=UTC)


def _one(conn: psycopg.Connection, sql: str, *args: Any) -> dict[str, Any]:
    return conn.execute(sql, args).fetchone()


def _world(conn: psycopg.Connection) -> dict[str, Any]:
    q = "SELECT p.patient_id, p.person_id FROM cm.patients p JOIN cm.persons x USING (person_id) WHERE x.token=%s"
    a, b = _one(conn, q, "P-0142"), _one(conn, q, "P-0087")
    doc = _one(conn, "SELECT person_id FROM cm.persons WHERE token='D-01'")["person_id"]
    tpl = _one(conn, "SELECT template_id FROM cm.templates WHERE status='approved' LIMIT 1")
    draft = _one(
        conn,
        "INSERT INTO cm.templates (key, lang, body) VALUES ('inv_draft_tpl','en','Hello') RETURNING template_id",
    )
    return {"A": a, "B": b, "doctor": doc, "tpl": tpl["template_id"], "draft": draft["template_id"]}


def _approval(conn: psycopg.Connection, w: dict[str, Any], pid: UUID | None = None) -> UUID:
    aid = uuid4()
    conn.execute(
        "INSERT INTO cm.approvals (approval_id, patient_id, thread_id, interrupt_id, graph_kind, tier, kind, "
        "payload, evidence, status, created_at, due_at, expires_at) VALUES "
        "(%s,%s,%s,'inv','deep','amber','needs_human',%s,'[]','pending',%s,%s,%s)",
        (aid, pid or w["A"]["patient_id"], f"inv-{aid}", Jsonb({"body": "hi", "audience": "patient"}),
         T, T + timedelta(hours=4), T + timedelta(days=2)),  # fmt: skip
    )
    return aid


def _decision(conn: psycopg.Connection, w: dict[str, Any], aid: UUID, action: str = "approve") -> UUID:
    via = "sweeper" if action == "expired" else "console"
    return _one(
        conn,
        "INSERT INTO cm.review_decisions (approval_id, doctor_id, action, reason, via, edited) "
        "VALUES (%s,%s,%s,'r',%s,%s) RETURNING decision_id",
        aid, w["doctor"], action, via, Jsonb({"body": "x"}) if action == "edit" else None,
    )["decision_id"]  # fmt: skip


_INS = (
    "INSERT INTO cm.outbox (kind, recipient_id, channel, body, approval_id, decision_id, template_id, dedup_key) "
    "VALUES (%s,%s,'telegram','text',%s,%s,%s,%s) RETURNING outbox_id"
)


def _ins(w: dict[str, Any], kind: str, aid: Any = None, did: Any = None, tid: Any = None) -> tuple:
    return (kind, w["A"]["person_id"], aid, did, tid, f"inv-{uuid4()}")


# ----------------------------------------------------------------------------- doctor gate
def test_gate_rejects_every_unauthorised_insert(raw: psycopg.Connection) -> None:
    w = _world(raw)
    a1, a2 = _approval(raw, w), _approval(raw, w)
    ok1 = _decision(raw, w, a1)
    rej = _decision(raw, w, a2, "reject")
    bad = {
        "nothing": _ins(w, "ai_message"),
        "approval_without_decision": _ins(w, "ai_message", a1),
        "decision_without_approval_or_template": _ins(w, "ai_message", None, ok1),
        "decision_of_other_approval": _ins(w, "ai_message", a2, ok1),
        "rejected_decision": _ins(w, "ai_message", a2, rej),
        "draft_template_system_kind": _ins(w, "checkin", tid=w["draft"]),
        "approved_template_non_system_kind": _ins(w, "ai_message", tid=w["tpl"]),
        "card_with_template_only": _ins(w, "card", tid=w["tpl"]),
        # a stray approve decision must not launder an unapproved template
        "draft_template_plus_foreign_decision": _ins(w, "checkin", None, ok1, w["draft"]),
    }
    for name, args in bad.items():
        err = expect_db_error(raw, _INS, args)
        assert isinstance(err, psycopg.errors.CheckViolation | psycopg.errors.RaiseException), name


def test_gate_allows_the_two_legal_shapes(raw: psycopg.Connection) -> None:
    w = _world(raw)
    aid = _approval(raw, w)
    did = _decision(raw, w, aid, "edit")
    assert raw.execute(_INS, _ins(w, "ai_message", aid, did)).fetchone()
    assert raw.execute(_INS, _ins(w, "checkin", tid=w["tpl"])).fetchone()


def test_gate_cannot_be_bypassed_by_update(raw: psycopg.Connection) -> None:
    w = _world(raw)
    a1, a2 = _approval(raw, w), _approval(raw, w)
    ok = _decision(raw, w, a1)
    rej = _decision(raw, w, a2, "reject")
    oid = raw.execute(_INS, _ins(w, "ai_message", a1, ok)).fetchone()["outbox_id"]
    sys_oid = raw.execute(_INS, _ins(w, "checkin", tid=w["tpl"])).fetchone()["outbox_id"]
    updates = [
        ("UPDATE cm.outbox SET decision_id=%s, approval_id=%s WHERE outbox_id=%s", (rej, a2, oid)),
        ("UPDATE cm.outbox SET approval_id=%s WHERE outbox_id=%s", (a2, oid)),
        ("UPDATE cm.outbox SET approval_id=NULL, decision_id=NULL WHERE outbox_id=%s", (oid,)),
        ("UPDATE cm.outbox SET template_id=%s WHERE outbox_id=%s", (w["draft"], sys_oid)),
        ("UPDATE cm.outbox SET kind='ai_message' WHERE outbox_id=%s", (sys_oid,)),
        # the doctor approved this exact text: it cannot be swapped afterwards
        ("UPDATE cm.outbox SET body='different text' WHERE outbox_id=%s", (oid,)),
        ("UPDATE cm.outbox SET body='different text' WHERE outbox_id=%s", (sys_oid,)),
    ]
    for sql, args in updates:
        expect_db_error(raw, sql, args)
    # allowed: delivery bookkeeping and the 30-day body purge
    raw.execute("UPDATE cm.outbox SET status='sending', locked_at=now(), attempts=1 WHERE outbox_id=%s", (oid,))
    raw.execute("UPDATE cm.outbox SET body=NULL WHERE outbox_id=%s", (oid,))


def test_gate_kind_list_matches_contract() -> None:
    from cm.contracts import review

    kinds = getattr(review, "SYSTEM_OUTBOX_KINDS", None)
    if kinds is None:
        pytest.skip("contract exposes no SYSTEM_OUTBOX_KINDS")
    from cm.core.db import transaction

    with transaction() as conn:
        db_kinds = conn.execute("SELECT cm.outbox_system_kinds() AS k").fetchone()["k"]
    assert set(db_kinds) == set(kinds)


# ----------------------------------------------------------------------------- append-only
@pytest.mark.parametrize("table", ["events", "consents", "audit_log"])
def test_append_only_tables_refuse_update_and_delete(raw: psycopg.Connection, table: str) -> None:
    row = raw.execute(f"SELECT ctid FROM cm.{table} LIMIT 1").fetchone()  # noqa: S608
    assert row, f"seed has no {table} rows"
    col = {"events": "source", "consents": "via", "audit_log": "actor"}[table]
    expect_db_error(raw, f"UPDATE cm.{table} SET {col}={col} WHERE ctid=%s", (row["ctid"],))  # noqa: S608
    expect_db_error(raw, f"DELETE FROM cm.{table} WHERE ctid=%s", (row["ctid"],))  # noqa: S608


@pytest.mark.parametrize("role", ["cm_app", "cm_engine"])
def test_app_roles_cannot_rewrite_history(raw: psycopg.Connection, role: str) -> None:
    raw.execute(f"SET LOCAL ROLE {role}")
    for sql in ("UPDATE cm.events SET source=source", "DELETE FROM cm.events",
                "TRUNCATE cm.events", "TRUNCATE cm.audit_log", "DELETE FROM cm.audit_log"):  # fmt: skip
        expect_db_error(raw, sql)


def test_append_only_trigger_survives_bulk_where_true(raw: psycopg.Connection) -> None:
    n = _one(raw, "SELECT count(*) AS n FROM cm.events")["n"]
    expect_db_error(raw, "UPDATE cm.events SET recorded_at = recorded_at - interval '1 day'")
    assert _one(raw, "SELECT count(*) AS n FROM cm.events")["n"] == n


# ----------------------------------------------------------------------------- patient isolation
def _patients(conn: psycopg.Connection) -> list[dict[str, Any]]:
    return conn.execute("SELECT patient_id, person_id FROM cm.patients ORDER BY patient_id").fetchall()


def test_reads_for_patient_a_never_return_b(raw: psycopg.Connection) -> None:
    far = datetime(2100, 1, 1, tzinfo=UTC)
    pts = _patients(raw)
    assert len(pts) >= 2
    for p in pts:
        pid = p["patient_id"]
        assert all(e["patient_id"] == pid for e in events_repo.query(pid, far, conn=raw))
        assert all(
            a["patient_id"] == pid
            for a in approvals_repo.queue(far, status=None, patient_id=pid, limit=500, conn=raw)
        )
        inbox = outbox_repo.inbox_for(p["person_id"], far, include_requests=True, conn=raw)
        assert all(o["recipient_id"] == p["person_id"] for o in inbox)
    total = sum(len(events_repo.query(p["patient_id"], far, conn=raw)) for p in pts)
    # every event belongs to a patient; reads skip superseded/tombstoned events, so visible <= stored
    assert total <= _one(raw, "SELECT count(*) AS n FROM cm.events")["n"]
    assert _one(raw, "SELECT count(*) AS n FROM cm.events e LEFT JOIN cm.patients p USING (patient_id) WHERE p.patient_id IS NULL")["n"] == 0


def test_missed_days_counts_only_that_patient(raw: psycopg.Connection) -> None:
    w = _world(raw)
    since, until = T - timedelta(days=400), T + timedelta(days=400)
    before_a = events_repo.missed_days(w["A"]["patient_id"], since, until, conn=raw)
    events_repo.append_event(
        events_repo.NewEvent(
            patient_id=w["B"]["patient_id"], type="DoseCheckin", occurred_at=T, recorded_at=T,
            source="system", idempotency_key=f"inv:{uuid4()}",
            payload={"status": "missed", "for_date": "1999-01-01"},
        ),  # fmt: skip
        conn=raw,
    )
    assert events_repo.missed_days(w["A"]["patient_id"], since, until, conn=raw) == before_a


# ----------------------------------------------------------------------------- as_of reads
def test_as_of_never_returns_later_recorded_rows(raw: psycopg.Connection) -> None:
    w = _world(raw)
    pid = w["A"]["patient_id"]
    r = random.Random(4242)  # noqa: S311  (seeded)
    mine: dict[UUID, tuple[datetime, datetime]] = {}
    for _ in range(40):
        occ = T + timedelta(hours=r.randint(-200, 200))
        rec = occ + timedelta(hours=r.choice([0, 1, 30, 100]))
        eid, _new = events_repo.append_event(
            events_repo.NewEvent(
                patient_id=pid, type="SymptomReport", occurred_at=occ, recorded_at=rec,
                source="system", idempotency_key=f"inv:{uuid4()}", payload={"items": []},
            ),  # fmt: skip
            conn=raw,
        )
        mine[eid] = (occ, rec)
    for _ in range(25):
        as_of = T + timedelta(hours=r.randint(-250, 350))
        rows = events_repo.query(pid, as_of, conn=raw)
        assert all(x["recorded_at"] <= as_of and x["occurred_at"] <= as_of for x in rows)
        got = {x["event_id"] for x in rows} & set(mine)
        want = {e for e, (o, rc) in mine.items() if o <= as_of and rc <= as_of}
        assert got == want


def test_missed_days_respects_recorded_at(raw: psycopg.Connection) -> None:
    """A miss that was only recorded after ``until`` was not knowable then (non-negotiable 9)."""
    w = _world(raw)
    pid = w["B"]["patient_id"]
    since, until = T - timedelta(days=1), T + timedelta(days=1)
    base = events_repo.missed_days(pid, since, until, conn=raw)
    events_repo.append_event(
        events_repo.NewEvent(
            patient_id=pid, type="DoseCheckin", occurred_at=T, recorded_at=until + timedelta(days=3),
            source="system", idempotency_key=f"inv:{uuid4()}",
            payload={"status": "missed", "for_date": "2026-01-20"},
        ),  # fmt: skip
        conn=raw,
    )
    assert events_repo.missed_days(pid, since, until, conn=raw) == base


def test_approvals_and_outbox_reads_hide_future_rows(raw: psycopg.Connection) -> None:
    w = _world(raw)
    aid = _approval(raw, w)
    did = _decision(raw, w, aid)
    raw.execute(
        _INS.replace("dedup_key)", "dedup_key, created_at)").replace("%s) RETURNING", "%s, %s) RETURNING"),
        (*_ins(w, "ai_message", aid, did), T + timedelta(days=1)),
    )
    assert approvals_repo.get(aid, T - timedelta(seconds=1), conn=raw) is None
    assert approvals_repo.get(aid, T, conn=raw) is not None
    assert outbox_repo.for_approval(aid, T, conn=raw) == []
    assert len(outbox_repo.for_approval(aid, T + timedelta(days=2), conn=raw)) == 1


# ----------------------------------------------------------------------------- budget day (IST)
def test_pg_budget_store_task_cost_uses_the_ist_day(pinned_clock: None) -> None:
    """At 01:30 IST (20:00 UTC the day before) the ad-hoc row written by add() must be the one read back."""
    from cm.core import clock
    from cm.core.budget_pg import PgUsageStore

    at = datetime(2031, 5, 4, 20, 0, tzinfo=UTC)
    clock.pin(at)
    try:
        store = PgUsageStore()
        day = clock.ist_date(at).isoformat()
        before = store.task_cost("adhoc")
        store.add(day=day, task_id="adhoc", task_type="other", patient_id=None, tokens_in=1,
                  tokens_out=1, cost_usd=0.125)  # fmt: skip
        assert store.task_cost("adhoc") == pytest.approx(before + 0.125)
    finally:
        from cm.core.db import transaction

        with transaction() as conn:
            clock.load_pin(conn)
