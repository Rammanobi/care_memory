"""Pure pipeline + engine conflict tests (no DB)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cm.memory.conflicts import self_report_vs_refill, weekday_pattern_conflict
from cm.memory.pipeline import compute_memory, prior_from_history

PID = UUID("11111111-1111-1111-1111-111111111111")
T0 = datetime(2026, 1, 5, 12, tzinfo=UTC)  # a Monday


def ev(type_, at, payload, rec=None, source="telegram"):
    return {
        "event_id": uuid4(),
        "type": type_,
        "occurred_at": at,
        "recorded_at": rec or at,
        "payload": payload,
        "source": source,
        "supersedes": None,
        "reporter_mode": "self",
    }


def checkins(days, status_of):
    return [
        ev("DoseCheckin", T0 + timedelta(days=i), {"status": status_of(i)}) for i in range(days)
    ]


def test_self_report_vs_refill_fires_with_c_ref():
    evs = [ev("Dispense", T0, {"days_supply": 5}, source="chemist")] + checkins(
        14, lambda i: "taken"
    )
    c = self_report_vs_refill(PID, T0 + timedelta(days=13, hours=1), evs)
    assert c and c.cref.startswith("C:") and c.refs[0] == c.cref and len(c.refs) >= 4
    assert all(r.startswith("E:") for r in c.refs[1:])
    assert c == self_report_vs_refill(PID, T0 + timedelta(days=13, hours=1), list(reversed(evs)))


def test_self_report_vs_refill_silent_when_covered_or_unknown():
    covered = [ev("Dispense", T0, {"days_supply": 60}, source="chemist")] + checkins(
        14, lambda i: "taken"
    )
    assert self_report_vs_refill(PID, T0 + timedelta(days=13), covered) is None
    assert (
        self_report_vs_refill(PID, T0 + timedelta(days=13), checkins(14, lambda i: "taken")) is None
    )


def test_weekday_pattern_conflict_needs_flag_and_recent_taken():
    # Mondays (i%7==0) missed for 4 weeks, then taken twice
    evs = checkins(49, lambda i: "missed" if i % 7 == 0 and i < 28 else "taken")
    as_of = T0 + timedelta(days=48, hours=1)
    got = weekday_pattern_conflict(PID, as_of, evs, ["Monday"])
    assert len(got) == 1 and got[0].kind == "weekday_pattern" and got[0].cref in got[0].refs
    assert weekday_pattern_conflict(PID, as_of, evs, []) == []


def test_compute_memory_beliefs_risk_and_determinism():
    evs = checkins(42, lambda i: "missed" if i % 7 == 3 else "taken")
    as_of = T0 + timedelta(days=41, hours=1)
    a = compute_memory(PID, evs, as_of, {}, treatment_start=T0.date())
    b = compute_memory(PID, list(reversed(evs)), as_of, {}, treatment_start=T0.date())
    assert a == b
    assert any(r["subject"] == "thu" for r in a.beliefs)
    assert a.risk and 0 <= a.risk.ci_low <= a.risk.ci_high <= 1
    assert a.features.weekday_miss["thu"][0] == 6


def test_no_risk_before_day_3():
    r = compute_memory(
        PID,
        checkins(2, lambda i: "taken"),
        T0 + timedelta(days=1, hours=1),
        {},
        treatment_start=T0.date(),
    )
    assert r.risk is None


def test_prior_from_history_low_run():
    from datetime import date

    rows = [
        {
            "as_of": date(2026, 1, d),
            "state": "hypothesis",
            "posterior": p,
            "first_seen": date(2026, 1, 1),
            "confirmed_at": None,
        }
        for d, p in ((1, 0.7), (2, 0.2), (3, 0.1))
    ]
    p = prior_from_history(rows)
    assert p["low_since"] == date(2026, 1, 2) and p["last_support"] == date(2026, 1, 1)
