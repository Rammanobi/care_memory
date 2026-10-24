"""Lane B: usage and caps numbers, settings, and DEMO_MODE-gated demo controls."""
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends

from cm.api.deps import ApiError, User, now, require_roles
from cm.api.portal_models import SimDayIn, UsageDay, UsageModeIn, UsageOut, UsageTask
from cm.contracts.admin import DetectorParams, RuleThresholds, SettingsIn, SettingsOut
from cm.core import clock
from cm.core.config import load_settings
from cm.core.db import transaction
from cm.store import settings_repo

router = APIRouter(prefix="/admin", tags=["admin"])
console = require_roles("doctor", "admin")
CHANNELS = ("telegram", "gmail", "calendar", "wearable")
_TASK_NAMES = {
    "nightly": "Nightly memory rebuild",
    "prepare_visit_list": "Narrator cards",
    "investigate": "Doctor Ask box",
    "ingest_event": "Other",
}
MODE_TARGET = {"GREEN": 4.1, "AMBER": 7.4, "RED": 9.35}
ADJUST_ID = "usage-demo-adjust"


def _caps() -> tuple[float, float]:
    return float(os.environ.get("DAILY_COST_CAP_USD", "10")), float(
        os.environ.get("MONTHLY_BUDGET_USD", "150")
    )


def _mode(spend: float, cap: float) -> str:
    ratio = spend / cap if cap else 1
    return "GREEN" if ratio < 0.6 else "AMBER" if ratio < 0.9 else "RED"


def _usage(conn: Any, at: Any) -> UsageOut:
    cap, budget = _caps()
    today = at.astimezone(clock.IST).date()
    rows = conn.execute(
        "SELECT (created_at AT TIME ZONE 'Asia/Kolkata')::date AS d, task_type, sum(cost_usd)::float AS cost, "
        "sum(attempt) AS retries FROM cm.task_runs WHERE cost_usd > 0 AND created_at <= %s "
        "AND created_at > %s GROUP BY 1, 2 ORDER BY 1",
        (at, at - timedelta(days=14)),
    ).fetchall()
    per_day: dict[Any, float] = {}
    for r in rows:
        per_day[r["d"]] = per_day.get(r["d"], 0.0) + r["cost"]
    today_rows = [r for r in rows if r["d"] == today]
    spend = round(per_day.get(today, 0.0), 2)
    tasks = []
    for r in today_rows:
        pct = round(100 * r["cost"] / spend) if spend else 0
        tasks.append(
            UsageTask(
                name=_TASK_NAMES.get(r["task_type"], "Other"),
                spend=round(r["cost"], 2),
                pct=pct,
                flag="watch" if pct >= 60 else "on budget",
            )
        )
    days = [
        UsageDay(d=f"D{i + 1}", spend=round(per_day.get(today - timedelta(days=13 - i), 0.0), 2))
        for i in range(14)
    ]
    return UsageOut(
        mode=_mode(spend, cap),
        today_spend=spend,
        today_cap=cap,
        budget_used=round(sum(per_day.values()), 2),
        budget=budget,
        days=days,
        tasks=tasks,
        retries=int(sum(r["retries"] or 0 for r in rows)),
        breaker=0,
        billing=0.0,
        provider_pct=min(100, round(100 * spend / cap * 0.75)) if cap else 0,
    )


@router.get("/usage", response_model=UsageOut)
def usage(_: User = Depends(console)) -> UsageOut:
    with transaction() as conn:
        return _usage(conn, now())


def _demo_only() -> None:
    if not load_settings().demo_mode:
        raise ApiError(404, "Not found", "not_found")


@router.post("/demo/usage-mode", response_model=UsageOut)
def set_usage_mode(body: UsageModeIn, _: User = Depends(require_roles("admin"))) -> UsageOut:
    _demo_only()
    at = now()
    with transaction() as conn:
        other = conn.execute(
            "SELECT COALESCE(sum(cost_usd),0)::float AS c FROM cm.task_runs WHERE task_id <> %s "
            "AND (created_at AT TIME ZONE 'Asia/Kolkata')::date = %s",
            (ADJUST_ID, at.astimezone(clock.IST).date()),
        ).fetchone()["c"]
        extra = max(0.0, round(MODE_TARGET[body.mode] - other, 2))
        conn.execute(
            "INSERT INTO cm.task_runs (task_id, task_type, state, cost_usd, created_at) "
            "VALUES (%s,'seed','succeeded',%s,%s) ON CONFLICT (task_id) DO UPDATE SET cost_usd = EXCLUDED.cost_usd",
            (ADJUST_ID, extra, at),
        )
        return _usage(conn, at)


@router.post("/demo/sim-day")
def set_sim_day(body: SimDayIn, _: User = Depends(require_roles("admin"))) -> dict[str, Any]:
    _demo_only()
    with transaction() as conn:
        row = conn.execute(
            "UPDATE cm.sim_clock SET sim_day=%s, max_computed_day=GREATEST(max_computed_day,%s) "
            "WHERE active RETURNING day0_date, sim_day",
            (body.sim_day, body.sim_day),
        ).fetchone()
        if not row:
            raise ApiError(404, "No active sim clock", "not_found")
        at = clock.sim_instant(row["day0_date"], row["sim_day"])
    clock.pin(at)
    return {"sim_day": body.sim_day, "now": at.isoformat()}


def _settings_out(conn: Any) -> SettingsOut:
    t = settings_repo.get_setting("thresholds", conn=conn)
    channels = {}
    for c in CHANNELS:
        s = settings_repo.get_setting(f"channels.{c}.enabled", conn=conn)
        channels[c] = bool(s["value"]) if s else False
    return SettingsOut(
        version=t["version"] if t else 0,
        values=RuleThresholds.model_validate(t["value"] if t else {}),
        detectors=DetectorParams(),
        channels=channels,
        updated_at=t["updated_at"] if t else None,
    )


@router.get("/settings", response_model=SettingsOut)
def get_settings(_: User = Depends(console)) -> SettingsOut:
    with transaction() as conn:
        return _settings_out(conn)


@router.put("/settings", response_model=SettingsOut)
def put_settings(body: SettingsIn, user: User = Depends(require_roles("admin"))) -> SettingsOut:
    with transaction() as conn:
        try:
            settings_repo.set_setting(
                "thresholds",
                body.values.model_dump(),
                expected_version=body.version or None,
                updated_by=user.person_id,
                updated_at=now(),
                conn=conn,
            )
        except settings_repo.VersionConflict as exc:
            raise ApiError(409, "Settings changed by someone else", "version_conflict") from exc
        return _settings_out(conn)
