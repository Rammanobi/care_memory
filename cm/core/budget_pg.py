"""Lane A: DB-backed UsageStore for the budget governor. Spend lives in cm.task_runs (tokens_in,
tokens_out, cost_usd), the same table the admin usage panel reads.

Install at API/worker startup:  ``install_governor()``.
"""
# ruff: noqa: S608

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from cm.core import budget as _budget
from cm.core import clock, db

_ALLOWED_TYPES = {
    "ingest_event", "nightly_patient", "investigate", "prepare_visit_list", "doctor_digest",
    "consent_change", "resume", "send", "drain_outbox", "checkins", "checkin_nudge", "digest",
    "visit_lists", "gmail_fetch", "gmail_watch_renew", "gmail_sweep", "portal_sync", "calendar_sync",
    "district_report", "nightly", "seed", "eval", "sweep", "migrate",
}  # fmt: skip
_DAY = "(created_at AT TIME ZONE 'Asia/Kolkata')::date = %s::date"


def _safe_id(task_id: str, day: str) -> str:
    tid = re.sub(r"[^A-Za-z0-9_-]", "_", task_id)[:480] or "adhoc"
    return f"adhoc-{day}" if tid == "adhoc" else tid


class PgUsageStore:
    """Implements cm.core.budget.UsageStore over cm.task_runs."""

    def add(self, *, day: str, task_id: str, task_type: str, patient_id: str | None,
            tokens_in: int, tokens_out: int, cost_usd: float) -> None:  # fmt: skip
        pid: UUID | None = None
        try:
            pid = UUID(patient_id) if patient_id else None
        except ValueError:
            pid = None  # tokenised ids are not task_runs FKs; per-patient tokens track UUIDs only
        ttype = task_type if task_type in _ALLOWED_TYPES else "ingest_event"
        at: datetime = clock.now()
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO cm.task_runs (task_id, task_type, patient_id, state, tokens_in, tokens_out, "
                "cost_usd, created_at, updated_at) VALUES (%s,%s,%s,'succeeded',%s,%s,%s,%s,%s) "
                "ON CONFLICT (task_id) DO UPDATE SET tokens_in = cm.task_runs.tokens_in + EXCLUDED.tokens_in, "
                "tokens_out = cm.task_runs.tokens_out + EXCLUDED.tokens_out, "
                "cost_usd = cm.task_runs.cost_usd + EXCLUDED.cost_usd, updated_at = EXCLUDED.updated_at",
                (_safe_id(task_id, day), ttype, pid, tokens_in, tokens_out, cost_usd, at, at),
            )

    def _one(self, sql: str, args: tuple = ()) -> float:
        with db.transaction() as conn:
            return float(conn.execute(sql, args).fetchone()["v"])

    def day_cost(self, day: str) -> float:
        return self._one(f"SELECT COALESCE(sum(cost_usd),0) AS v FROM cm.task_runs WHERE {_DAY}", (day,))

    def total_cost(self) -> float:
        return self._one("SELECT COALESCE(sum(cost_usd),0) AS v FROM cm.task_runs")

    def task_cost(self, task_id: str) -> float:
        return self._one(
            "SELECT COALESCE(sum(cost_usd),0) AS v FROM cm.task_runs WHERE task_id=%s",
            (_safe_id(task_id, clock.ist_date(clock.now()).isoformat()),),  # IST, as in add()
        )

    def patient_tokens(self, day: str, patient_id: str) -> int:
        try:
            pid = UUID(patient_id)
        except ValueError:
            return 0
        return int(self._one(
            f"SELECT COALESCE(sum(tokens_in+tokens_out),0) AS v FROM cm.task_runs WHERE patient_id=%s AND {_DAY}",
            (pid, day),
        ))  # fmt: skip

    def cost_by_task_type(self, day: str) -> dict[str, float]:
        with db.transaction() as conn:
            rows = conn.execute(
                f"SELECT task_type, sum(cost_usd)::float AS c FROM cm.task_runs WHERE {_DAY} "
                "AND cost_usd > 0 GROUP BY task_type",
                (day,),
            ).fetchall()
        return {r["task_type"]: r["c"] for r in rows}


def install_governor() -> _budget.BudgetGovernor:
    """Build the governor from CM_BUDGET_* env with the DB store and register it with cm.core.llm."""
    from cm.core import llm

    gov = _budget.BudgetGovernor(
        _budget.BudgetLimits.from_env(),
        _budget.PriceTable.from_env(),
        PgUsageStore(),
        clock=lambda: clock.now().astimezone(clock.IST),  # day boundaries are IST, as in SQL
    )
    llm.set_governor(gov)
    return gov
