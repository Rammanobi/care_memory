"""AI-runtime repo functions (kept in a new file so lane A's repos stay untouched)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from cm.core import clock
from cm.core.db import transaction
from cm.store import approvals_repo


def resolve_patient(code: str, *, conn: Any = None) -> tuple[UUID, str]:
    """'PT-0142' or 'P-0142' -> (patient_id, token)."""
    if conn is None:
        with transaction() as c:
            return resolve_patient(code, conn=c)
    token = "P-" + code.split("-", 1)[1] if code.upper().startswith("PT-") else code
    row = conn.execute(
        "SELECT p.patient_id, per.token FROM cm.patients p JOIN cm.persons per ON per.person_id=p.person_id "
        "WHERE per.token=%s",
        (token,),
    ).fetchone()
    if not row:
        raise LookupError(f"unknown patient {code}")
    return row["patient_id"], row["token"]


def sim_day0(*, conn: Any = None) -> tuple[date | None, int]:
    """(day0 date, current sim day) of the active sim clock, or (None, 0)."""
    if conn is None:
        with transaction() as c:
            return sim_day0(conn=c)
    row = conn.execute("SELECT day0_date, sim_day FROM cm.sim_clock WHERE active").fetchone()
    return (row["day0_date"], int(row["sim_day"])) if row else (None, 0)


def due_for_tier(tier: str, created: datetime) -> datetime:
    """Red created+4h, Amber next 12:00 IST, Green end of day (IST)."""
    local = created.astimezone(clock.IST)
    if tier == "red":
        return created + timedelta(hours=4)
    if tier == "amber":
        d = local.date() + (timedelta(days=1) if local.time() >= time(12, 0) else timedelta())
        return datetime.combine(d, time(12, 0), tzinfo=clock.IST)
    return datetime.combine(local.date(), time(23, 59), tzinfo=clock.IST)


def create_card_approval(*, patient_id: UUID, thread_id: str, interrupt_id: str, tier: str, payload: dict[str, Any],
                         evidence: list[dict[str, Any]], created_at: datetime) -> UUID:
    """Pending doctor-facing card in the approvals queue. Never writes the outbox."""
    return approvals_repo.upsert(
        {
            "patient_id": patient_id, "thread_id": thread_id, "interrupt_id": interrupt_id,
            "graph_kind": "deep", "tier": tier, "kind": "card", "payload": payload, "evidence": evidence,
            "created_at": created_at, "due_at": due_for_tier(tier, created_at),
            "expires_at": created_at + timedelta(hours=48),
        }
    )


def task_run_totals(task_id: str) -> dict[str, Any]:
    with transaction() as c:
        row = c.execute(
            "SELECT tokens_in, tokens_out, cost_usd::float AS cost_usd FROM cm.task_runs WHERE task_id=%s",
            (task_id,),
        ).fetchone()
    return dict(row) if row else {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}


def outbox_count(approval_id: UUID) -> int:
    with transaction() as c:
        return int(c.execute("SELECT count(*) AS n FROM cm.outbox WHERE approval_id=%s", (approval_id,)).fetchone()["n"])


def pending_card(patient_id: UUID) -> UUID | None:
    with transaction() as c:
        row = c.execute(
            "SELECT approval_id FROM cm.approvals WHERE patient_id=%s AND kind='card' AND status='pending' "
            "AND payload->>'subkind'='nightly_card' LIMIT 1", (patient_id,)).fetchone()
    return row["approval_id"] if row else None


def approval_tier(ids: list[str]) -> str | None:
    if not ids:
        return None
    with transaction() as c:
        row = c.execute("SELECT tier FROM cm.approvals WHERE approval_id=%s", (UUID(ids[0]),)).fetchone()
    return row["tier"] if row else None
