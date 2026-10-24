"""Memory-engine persistence (features_daily, beliefs, belief_evidence, risk_scores, conflicts).

New file next to ``ai_repo`` so lane A's repos stay untouched. Every write is an idempotent upsert keyed by the
table primary key, so running the nightly pipeline twice for one ``as_of`` leaves identical rows
(``computed_at`` only moves when the stored content actually changes).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from cm.core.db import transaction


def list_patient_ids(*, conn: Any = None) -> list[UUID]:
    if conn is None:
        with transaction() as c:
            return list_patient_ids(conn=c)
    rows = conn.execute("SELECT patient_id FROM cm.patients ORDER BY patient_id").fetchall()
    return [r["patient_id"] for r in rows]


# --------------------------------------------------------------------------- features / risk
def upsert_features(
    pid: UUID,
    as_of: date,
    features: dict[str, Any],
    engine_version: str,
    computed_at: datetime,
    *,
    conn: Any,
) -> None:
    conn.execute(
        "INSERT INTO cm.features_daily (patient_id, as_of, features, computed_at, engine_version) "
        "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (patient_id, as_of) DO UPDATE SET features=EXCLUDED.features, "
        "engine_version=EXCLUDED.engine_version, computed_at=EXCLUDED.computed_at "
        "WHERE (cm.features_daily.features, cm.features_daily.engine_version) "
        "IS DISTINCT FROM (EXCLUDED.features, EXCLUDED.engine_version)",
        (pid, as_of, Jsonb(features), computed_at, engine_version),
    )


def upsert_risk(
    pid: UUID, as_of: date, risk: dict[str, Any], computed_at: datetime, *, conn: Any
) -> None:
    conn.execute(
        "INSERT INTO cm.risk_scores (patient_id, as_of, p, ci_low, ci_high, drivers, model_version, computed_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (patient_id, as_of) DO UPDATE SET p=EXCLUDED.p, "
        "ci_low=EXCLUDED.ci_low, ci_high=EXCLUDED.ci_high, drivers=EXCLUDED.drivers, "
        "model_version=EXCLUDED.model_version, computed_at=EXCLUDED.computed_at "
        "WHERE (cm.risk_scores.p, cm.risk_scores.ci_low, cm.risk_scores.ci_high, cm.risk_scores.drivers, "
        "cm.risk_scores.model_version) IS DISTINCT FROM (EXCLUDED.p, EXCLUDED.ci_low, EXCLUDED.ci_high, "
        "EXCLUDED.drivers, EXCLUDED.model_version)",
        (
            pid,
            as_of,
            risk["p"],
            risk["ci_low"],
            risk["ci_high"],
            Jsonb(risk["drivers"]),
            risk["model_version"],
            computed_at,
        ),
    )


def get_risk(pid: UUID, as_of: date, *, conn: Any) -> dict[str, Any] | None:
    return conn.execute(
        "SELECT p, ci_low, ci_high, drivers, model_version FROM cm.risk_scores WHERE patient_id=%s AND as_of=%s",
        (pid, as_of),
    ).fetchone()


def get_features(pid: UUID, as_of: date, *, conn: Any) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT features FROM cm.features_daily WHERE patient_id=%s AND as_of=%s", (pid, as_of)
    ).fetchone()
    return row["features"] if row else None


# --------------------------------------------------------------------------- beliefs
def belief_history(pid: UUID, before: date, *, conn: Any) -> dict[UUID, list[dict[str, Any]]]:
    """Stored belief rows with ``as_of < before`` (strict, so a re-run of the same day sees the same past)."""
    rows = conn.execute(
        "SELECT * FROM cm.beliefs WHERE patient_id=%s AND as_of < %s ORDER BY belief_id, as_of",
        (pid, before),
    ).fetchall()
    out: dict[UUID, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["belief_id"], []).append(r)
    return out


def upsert_belief(row: dict[str, Any], *, conn: Any) -> None:
    conn.execute(
        "INSERT INTO cm.beliefs (belief_id, as_of, patient_id, kind, subject, state, posterior, ci_low, ci_high, "
        "n_instances, first_seen, confirmed_at, retired_at, retired_reason) "
        "VALUES (%(belief_id)s,%(as_of)s,%(patient_id)s,%(kind)s,%(subject)s,%(state)s,%(posterior)s,%(ci_low)s,"
        "%(ci_high)s,%(n_instances)s,%(first_seen)s,%(confirmed_at)s,%(retired_at)s,%(retired_reason)s) "
        "ON CONFLICT (belief_id, as_of) DO UPDATE SET state=EXCLUDED.state, posterior=EXCLUDED.posterior, "
        "ci_low=EXCLUDED.ci_low, ci_high=EXCLUDED.ci_high, n_instances=EXCLUDED.n_instances, "
        "first_seen=EXCLUDED.first_seen, confirmed_at=EXCLUDED.confirmed_at, retired_at=EXCLUDED.retired_at, "
        "retired_reason=EXCLUDED.retired_reason",
        row,
    )


def add_belief_evidence(
    belief_id: UUID, event_ids: Iterable[UUID], role: str = "support", *, conn: Any
) -> None:
    for eid in sorted(set(event_ids), key=str):
        conn.execute(
            "INSERT INTO cm.belief_evidence (belief_id, event_id, role) VALUES (%s,%s,%s) "
            "ON CONFLICT (belief_id, event_id) DO NOTHING",
            (belief_id, eid, role),
        )


def beliefs_as_of(pid: UUID, as_of: date, *, conn: Any) -> list[dict[str, Any]]:
    return conn.execute(
        "SELECT * FROM cm.beliefs WHERE patient_id=%s AND as_of=%s ORDER BY belief_id", (pid, as_of)
    ).fetchall()


# --------------------------------------------------------------------------- conflicts
def stored_conflicts(pid: UUID, *, conn: Any) -> list[dict[str, Any]]:
    return conn.execute(
        "SELECT conflict_id, patient_id, rule, tier, title, evidence_ids, opened_as_of, closed_as_of "
        "FROM cm.conflicts WHERE patient_id=%s ORDER BY opened_as_of, rule, conflict_id",
        (pid,),
    ).fetchall()


def upsert_conflict(row: dict[str, Any], *, conn: Any) -> None:
    conn.execute(
        "INSERT INTO cm.conflicts (conflict_id, patient_id, rule, tier, title, evidence_ids, opened_as_of, "
        "closed_as_of) VALUES (%(conflict_id)s,%(patient_id)s,%(rule)s,%(tier)s,%(title)s,%(evidence_ids)s,"
        "%(opened_as_of)s,%(closed_as_of)s) ON CONFLICT (conflict_id) DO UPDATE SET tier=EXCLUDED.tier, "
        "title=EXCLUDED.title, evidence_ids=EXCLUDED.evidence_ids, opened_as_of=EXCLUDED.opened_as_of, "
        "closed_as_of=EXCLUDED.closed_as_of",
        {**row, "evidence_ids": Jsonb(list(row["evidence_ids"]))},
    )
