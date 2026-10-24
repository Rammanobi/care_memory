"""Event-row builders for the R1-R6 tests (shape of ``cm.events`` rows: envelope + ``payload``)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID, uuid4

from cm.contracts.admin import RuleThresholds
from cm.core.clock import IST

PID = UUID("11111111-2222-4333-8444-555555555555")
OTHER_PID = UUID("99999999-2222-4333-8444-555555555555")
START = date(2026, 1, 5)
PATIENT = {"patient_id": PID, "treatment_start": START}
TH = RuleThresholds()


def d(day: int) -> date:
    return START + timedelta(days=day)


def at(day: int, hour: int = 18) -> datetime:
    return datetime.combine(d(day), time(hour, 0), tzinfo=IST)


def ev(
    etype: str,
    day: int,
    rec: int | None = None,
    *,
    rmode: str = "record",
    source: str = "system",
    pid: UUID = PID,
    supersedes: UUID | None = None,
    event_id: UUID | None = None,
    **payload: Any,
) -> dict[str, Any]:
    return {
        "event_id": event_id or uuid4(),
        "patient_id": pid,
        "type": etype,
        "occurred_at": at(day),
        "recorded_at": at(day if rec is None else rec, 19),
        "source": source,
        "reporter_mode": rmode,
        "supersedes": supersedes,
        "idempotency_key": f"t:{uuid4()}",
        "payload": payload,
    }


def regimen(day: int = 0, line: str = "first", **kw: Any) -> dict[str, Any]:
    return ev(
        "RegimenChange",
        day,
        regimen_to=f"{line}_line",
        line=line,
        effective_date=d(day).isoformat(),
        **kw,
    )


def dispense(
    day: int, rec: int | None = None, tablets: int = 120, days_supply: int | None = 30
) -> dict[str, Any]:
    return ev("Dispense", day, rec, source="chemist", tablets=tablets, days_supply=days_supply)


def taken(
    day: int, *, mode: str = "self", status: str = "taken", rec: int | None = None
) -> dict[str, Any]:
    return ev(
        "DoseCheckin",
        day,
        rec,
        rmode=mode,
        source="telegram",
        status=status,
        for_date=d(day).isoformat(),
    )


def prompt(day: int) -> dict[str, Any]:
    return ev(
        "CheckinPrompt",
        day,
        outbox_id=str(uuid4()),
        channel="telegram",
        for_date=d(day).isoformat(),
        sent_at=at(day, 9).isoformat(),
    )


def visit(day: int, mode: str = "witnessed") -> dict[str, Any]:
    return ev(
        "SupporterVisit",
        day,
        rmode="witnessed" if mode == "witnessed" else "told",
        mode=mode,
        source="supporter",
        visit_date=d(day).isoformat(),
    )


def contact(day: int, cid: UUID, action: str, rec: int | None = None, **kw: Any) -> dict[str, Any]:
    return ev(
        "HouseholdContactEvent",
        day,
        rec,
        rmode="told",
        source="supporter",
        contact_id=str(cid),
        action=action,
        **kw,
    )


def rules_of(conflicts: list[Any], rule: str) -> list[Any]:
    return [c for c in conflicts if c.rule == rule]
