"""Lane F: quiet hours 21:00-07:00 IST (red alerts to doctor/STS are exempt; the caller decides)."""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
START = time(21, 0)
END = time(7, 0)


def in_quiet_hours(when: datetime) -> bool:
    """True when ``when`` (tz-aware) falls in 21:00-07:00 IST."""
    if os.environ.get("DEMO_IGNORE_QUIET_HOURS") == "1" and os.environ.get("CM_ENV") == "dev":
        return False  # demo override, dev only
    t = when.astimezone(IST).time()
    return t >= START or t < END


def next_open(when: datetime) -> datetime:
    """First instant at or after ``when`` outside quiet hours."""
    if not in_quiet_hours(when):
        return when
    local = when.astimezone(IST)
    day = local.date() if local.time() < END else local.date() + timedelta(days=1)
    return datetime.combine(day, END, tzinfo=IST).astimezone(when.tzinfo)
