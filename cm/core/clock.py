"""Lane A: the only clock. Honours a pinned sim time (global or per clinic); never call datetime.now()."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
_pins: dict[str | None, datetime] = {}


def sim_instant(day0: date, sim_day: int) -> datetime:
    """The pinned instant for a sim day: 18:00 IST."""
    return datetime.combine(day0 + timedelta(days=sim_day), time(18, 0), tzinfo=IST).astimezone(UTC)


def pin(at: datetime, clinic_id: object | None = None) -> None:
    _pins[None if clinic_id is None else str(clinic_id)] = at


def unpin(clinic_id: object | None = None) -> None:
    _pins.pop(None if clinic_id is None else str(clinic_id), None)


def now(clinic_id: object | None = None) -> datetime:
    """Pinned time for the clinic, else the global pin, else real UTC time."""
    if clinic_id is not None and str(clinic_id) in _pins:
        return _pins[str(clinic_id)]
    if None in _pins:
        return _pins[None]
    return datetime.now(UTC)


def load_pin(conn: object) -> datetime | None:
    """Pin the global clock from the active sim_clock row (if any)."""
    row = conn.execute(  # type: ignore[attr-defined]
        "SELECT day0_date, sim_day FROM cm.sim_clock WHERE active"
    ).fetchone()
    if not row:
        return None
    at = sim_instant(row["day0_date"], row["sim_day"])
    pin(at)
    return at


def current_sim_day(conn: object) -> int:
    row = conn.execute("SELECT sim_day FROM cm.sim_clock WHERE active").fetchone()  # type: ignore[attr-defined]
    return int(row["sim_day"]) if row else 0
