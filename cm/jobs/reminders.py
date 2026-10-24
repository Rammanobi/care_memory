"""Integration: daily check-in producer.

Creates one routine ``checkin`` outbox row per active Telegram-bound patient per IST day, from the
approved template ``daily_checkin_reminder_v1`` (system kind: a template id is the authority, no
per-message doctor approval). Skips patients without ``daily_checkin`` consent; rows created inside quiet
hours are scheduled for the next opening. dedup_key = checkin:<person>:<date>, so re-running is safe.

Run:  python -m cm.jobs.reminders --now
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from cm.channels import tg_callback
from cm.channels.adapters_pg import PgConsents
from cm.core import clock, db
from cm.core.config import REPO_ROOT
from cm.core.logging import get_logger
from cm.router.banned import find_banned
from cm.router.quiet_hours import in_quiet_hours, next_open
from cm.store import channels_repo, outbox_repo

log = get_logger()
TEMPLATE_ID = "daily_checkin_reminder_v1"
YAML_PATH = Path(REPO_ROOT) / "cm" / "router" / "templates" / "reminders.yaml"
FALLBACK_NAME = "friend"


def load_template(template_id: str = TEMPLATE_ID) -> dict[str, Any]:
    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    for t in data["templates"]:
        if t["id"] == template_id:
            if not t.get("doctor_approved"):
                raise ValueError(f"template {template_id} is not doctor approved")
            return t
    raise KeyError(template_id)


def _text(tpl: dict[str, Any], lang: str) -> tuple[str, str]:
    langs = tpl["languages"]
    use = lang if lang in langs and "telegram" in langs[lang] else "en"
    return use, langs[use]["telegram"]


def greeting_name(first_name: str | None) -> str:
    """The name to greet with: the decrypted first name, or the neutral fallback when absent or unsafe."""
    if not first_name or find_banned(first_name):
        return FALLBACK_NAME
    return first_name


def produce(at: datetime | None = None) -> dict[str, int]:
    at = at or clock.now()
    day = at.astimezone(clock.IST).date()
    tpl = load_template()
    consents = PgConsents()
    out = {"created": 0, "existing": 0, "no_consent": 0, "no_template": 0}
    for t in channels_repo.reminder_targets():
        if not consents.has_consent(t["person_id"], "telegram", "daily_checkin", at):
            out["no_consent"] += 1
            continue
        lang, raw = _text(tpl, t["lang"])
        with db.transaction() as conn:
            tid = channels_repo.ensure_template(
                TEMPLATE_ID, lang, raw, list(tpl.get("placeholders", [])), at, conn=conn
            )
            if tid is None:
                out["no_template"] += 1
                continue
            oid = uuid4()
            got = outbox_repo.enqueue(
                {
                    "outbox_id": oid,
                    "kind": "checkin",
                    "recipient_id": t["person_id"],
                    "channel": "telegram",
                    "body": raw.replace("{first_name}", greeting_name(t.get("first_name"))),
                    "template_id": tid,
                    "next_attempt_at": next_open(at) if in_quiet_hours(at) else at,
                    "created_at": at,
                    "for_date": day,
                    "meta": {"reply_markup": tg_callback.dose_buttons(oid.hex), "template": TEMPLATE_ID},
                    "dedup_key": f"checkin:{t['person_id']}:{day}",
                },
                conn=conn,
            )
        out["created" if got == oid else "existing"] += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Create today's check-in reminders")
    ap.add_argument("--now", action="store_true", help="produce for the current clock time")
    ap.parse_args()
    print(produce())
    db.close_pool()


if __name__ == "__main__":
    main()
