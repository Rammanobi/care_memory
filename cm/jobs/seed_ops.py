"""Lane B: seed templates, settings (thresholds + channel switches) and 14 days of usage (task_runs)."""

from __future__ import annotations

import random
import re
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING

from psycopg.types.json import Jsonb

from cm.contracts.admin import RuleThresholds
from cm.core import clock
from cm.core.ids import det_id
from cm.store import settings_repo

if TYPE_CHECKING:
    from cm.jobs.seed import Ctx

TASK_TYPES = {
    "Nightly memory rebuild": "nightly",
    "Narrator cards": "prepare_visit_list",
    "Doctor Ask box": "investigate",
    "Other": "ingest_event",
}
CHANNEL_ON = {"telegram": True, "gmail": True, "calendar": False, "wearable": False}


def seed_templates(ctx: Ctx) -> None:
    for t in ctx.state["templates"]:
        key = re.sub(r"[^a-z0-9]+", "_", t["name"].lower()).strip("_")
        slots = sorted(set(re.findall(r"\{(\w+)\}", t["text"])))
        ctx.conn.execute(
            "INSERT INTO cm.templates (template_id, key, lang, body, slots, tier, status, approved_by, approved_at) "
            "VALUES (%s,%s,'en',%s,%s,'green','approved',%s,%s) ON CONFLICT DO NOTHING",
            (det_id("template", t["id"]), key, t["text"], slots, ctx.doctor_id, ctx.sim_now),
        )
    ctx.bump("templates", len(ctx.state["templates"]))


def seed_settings(ctx: Ctx) -> None:
    ctx.conn.execute(
        "INSERT INTO cm.settings (key, value, updated_by, updated_at) VALUES ('thresholds', %s, %s, %s) "
        "ON CONFLICT DO NOTHING",
        (Jsonb(RuleThresholds().model_dump()), ctx.doctor_id, ctx.sim_now),
    )
    for ch, on in CHANNEL_ON.items():
        ctx.conn.execute(
            "INSERT INTO cm.settings (key, value, updated_by, updated_at) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (f"channels.{ch}.enabled", Jsonb(on), ctx.doctor_id, ctx.sim_now),
        )
    settings_repo.clear_cache()


def seed_usage(ctx: Ctx, seed: int) -> None:
    """14 days of task_runs whose costs add up to the UI usage numbers (today = GREEN, 4.1)."""
    usage = ctx.state["usage"]
    rng = random.Random(seed)  # noqa: S311 (deterministic seed data, not security)
    shares = {
        t["name"]: t["spend"] / sum(x["spend"] for x in usage["tasks"]) for t in usage["tasks"]
    }
    n = 0
    for i, day in enumerate(usage["days"]):
        d = ctx.today - timedelta(days=13 - i)
        total = day["spend"] if i < 13 else sum(t["spend"] for t in usage["tasks"])
        for name, share in shares.items():
            tid = f"usage-{d.isoformat()}-{TASK_TYPES[name]}"
            cost = round(total * share, 4)
            at = datetime.combine(d, time(6, rng.randint(0, 50)), tzinfo=clock.IST)
            ctx.conn.execute(
                "INSERT INTO cm.task_runs (task_id, task_type, state, attempt, tokens_in, tokens_out, cost_usd, created_at) "
                "VALUES (%s,%s,'succeeded',%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (
                    tid,
                    TASK_TYPES[name],
                    1 if n % 8 == 0 else 0,
                    int(cost * 90000),
                    int(cost * 20000),
                    cost,
                    at,
                ),
            )
            n += 1
    ctx.bump("usage_task_runs", n)


def seed_ops(ctx: Ctx, seed: int) -> None:
    seed_templates(ctx)
    seed_settings(ctx)
    seed_usage(ctx, seed)
