"""Lane B: usage and caps numbers, settings, and DEMO_MODE-gated demo controls."""
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends

from cm.api.deps import ApiError, User, now, require_roles
from cm.api.portal_models import (
    ChannelStateOut,
    NightlyRunIn,
    NightlyRunOut,
    SimDayIn,
    UsageDay,
    UsageModeIn,
    UsageOut,
    UsageTask,
)
from cm.contracts.admin import DetectorParams, RuleThresholds, SettingsIn, SettingsOut
from cm.core import clock
from cm.core import tasks as core_tasks
from cm.core.config import load_settings
from cm.core.db import transaction
from cm.store import channels_repo, settings_repo

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


def _merge_tasks(today_rows: list[dict[str, Any]], spend: float) -> list[UsageTask]:
    """One row per display name (task types that share a name are merged), biggest first, stable order.

    Sums stay unrounded until the end so the rows add up to the day total (to the cent).
    """
    by_name: dict[str, float] = {}
    for r in today_rows:
        name = _TASK_NAMES.get(r["task_type"], "Other")
        by_name[name] = by_name.get(name, 0.0) + float(r["cost"])
    out = []
    for name, cost in sorted(by_name.items(), key=lambda kv: (-kv[1], kv[0])):
        pct = round(100 * cost / spend) if spend else 0
        out.append(
            UsageTask(
                name=name,
                spend=round(cost, 2),
                pct=pct,
                flag="watch" if pct >= 60 else "on budget",
            )
        )
    return out


def _usage(conn: Any, at: Any) -> UsageOut:
    cap, budget = _caps()
    today = at.astimezone(clock.IST).date()
    rows = conn.execute(
        "SELECT (created_at AT TIME ZONE 'Asia/Kolkata')::date AS d, task_type, sum(cost_usd)::float AS cost, "
        "sum(attempt) AS retries FROM cm.task_runs WHERE cost_usd > 0 AND created_at <= %s "
        "AND created_at > %s GROUP BY 1, 2 ORDER BY 1, 2",
        (at, at - timedelta(days=14)),
    ).fetchall()
    per_day: dict[Any, float] = {}
    for r in rows:
        per_day[r["d"]] = per_day.get(r["d"], 0.0) + r["cost"]
    spend = round(per_day.get(today, 0.0), 2)
    tasks = _merge_tasks([r for r in rows if r["d"] == today], spend)
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


def _channel_states(conn: Any, real_now: datetime) -> list[ChannelStateOut]:
    tg = conn.execute(
        "SELECT count(*) FILTER (WHERE status='active') AS active, max(bound_at) AS last_bound "
        "FROM cm.channel_bindings WHERE channel='telegram'"
    ).fetchone()
    last = conn.execute(
        "SELECT max(recorded_at) AS t FROM cm.events WHERE idempotency_key LIKE 'tg:%%'"
    ).fetchone()["t"]
    token_set = bool(os.environ.get("TELEGRAM_BOT_TOKEN"))
    seen = bool(last) and real_now - last <= timedelta(hours=24)
    username = os.environ.get("TELEGRAM_BOT_USERNAME", "").lstrip("@") or None
    out = [
        ChannelStateOut(
            name="telegram",
            connected=token_set and (tg["active"] > 0 or seen),
            detail=(
                f"Bot @{username}" if username else "Bot token set" if token_set else "No bot token"
            )
            + f"; {tg['active']} active binding(s)"
            + ("; messages seen in the last 24 h" if seen else "; no recent messages"),
            bot_username=username,
            active_bindings=int(tg["active"]),
            last_seen_at=last,
            recently_seen=seen,
        )
    ]
    gmail_on = bool(os.environ.get("GMAIL_REFRESH_TOKEN") and os.environ.get("GMAIL_MAILBOX"))
    cal_on = gmail_on and bool(os.environ.get("GOOGLE_CALENDAR_ID"))
    out.append(
        ChannelStateOut(
            name="gmail", connected=gmail_on, detail="Connected" if gmail_on else "Not connected"
        )
    )
    out.append(
        ChannelStateOut(
            name="calendar", connected=cal_on, detail="Connected" if cal_on else "Not connected"
        )
    )
    return out


@router.get("/channels", response_model=list[ChannelStateOut])
def get_channels(_: User = Depends(console)) -> list[ChannelStateOut]:
    with transaction() as conn:
        return _channel_states(conn, datetime.now(UTC))


def _live_allowed() -> bool:
    """Live LLM only for non-real data, and only while the budget governor is not RED."""
    if os.environ.get("CM_DATA_CLASS", "synthetic").lower() not in ("mock", "synthetic"):
        return False
    from cm.core.budget import BudgetState
    from cm.core.budget_pg import install_governor

    return install_governor().state() is not BudgetState.RED


@router.post("/demo/run-nightly", response_model=NightlyRunOut)
def run_nightly(body: NightlyRunIn, _: User = Depends(require_roles("admin"))) -> NightlyRunOut:
    _demo_only()
    token = body.patient.strip().upper()
    m = re.fullmatch(r"(?:PT|P)-?(\d{2,4})", token)
    who = channels_repo.person_by_token(f"P-{m.group(1)}") if m else None
    if not who:
        raise ApiError(404, "No such patient", "not_found")
    live = body.live and _live_allowed()
    task_id = f"nightly-{token.replace('-', '')}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
    core_tasks.enqueue(
        "agent-runs", task_id, {"kind": "nightly", "patient": f"P-{m.group(1)}", "live": live}
    )
    return NightlyRunOut(status="queued", task_id=task_id, patient=f"PT-{m.group(1)}", live=live)
