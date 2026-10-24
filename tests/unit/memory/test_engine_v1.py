from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from cm.memory.detectors.refill import refill_coverage
from cm.memory.detectors.trust import reporter_trust
from cm.memory.detectors.weekday import detect_weekday_misses, weekday_effect
from cm.memory.lifecycle import BeliefState, advance_belief_state
from cm.memory.missed import missed_dose_features
from cm.memory.risk import score_risk

T0 = datetime(2026, 1, 5, 12, tzinfo=UTC)


def ev(type_, at, payload, rec=None):
    return {
        "event_id": uuid4(),
        "type": type_,
        "occurred_at": at,
        "recorded_at": rec or at,
        "payload": payload,
        "source": "telegram",
        "supersedes": None,
    }


def test_missed_features_and_as_of_hides_future():
    evs = [
        ev("DoseCheckin", T0 + timedelta(days=i), {"status": "missed" if i % 2 else "taken"})
        for i in range(6)
    ]
    as_of = T0 + timedelta(days=5, hours=1)
    f = missed_dose_features(evs, as_of)
    assert f.missed_7d == 3 and f.taken_7d == 3
    early = missed_dose_features(evs, T0 + timedelta(hours=1))
    assert early.missed_7d == 0 and early.checkins_total == 1
    assert f.as_dict() == missed_dose_features(evs, as_of).as_dict()


def test_weekday_ravi_like_confirmed_and_deterministic():
    a = weekday_effect("P1", "Thursday", T0, 6, 8, 3, 48)
    assert a.state == "confirmed" and a.posterior >= 0.9 and a.ci_low < a.ci_high
    assert a == weekday_effect("P1", "Thursday", T0, 6, 8, 3, 48)


def test_weekday_no_pattern_and_detect():
    assert weekday_effect("P1", "Monday", T0, 0, 8, 3, 48).state is None
    wm = {"Monday": (0, 8), "Tuesday": (1, 8), "Thursday": (6, 8), "Friday": (0, 8)}
    assert [b.weekday for b in detect_weekday_misses("P1", T0, wm)] == ["Thursday"]
    with pytest.raises(ValueError):
        weekday_effect("P1", "Monday", T0, 9, 8, 0, 8)


def test_refill_gap_as_of_and_unknown():
    d = ev("Dispense", T0, {"days_supply": 10})
    assert refill_coverage([d], T0 + timedelta(days=15)).gap_days == 5
    assert refill_coverage([d], T0 + timedelta(days=5)).covered is True
    assert refill_coverage([d], T0 - timedelta(days=1)).covered is None
    assert refill_coverage([], T0).gap_days == 0


def test_trust_interval_narrows_and_states():
    few = reporter_trust("P1", "self", T0, 2, 3)
    many = reporter_trust("P1", "self", T0, 4, 12)
    assert (many.ci_high - many.ci_low) < (few.ci_high - few.ci_low)
    assert few.state == "hypothesis" and many.state == "confirmed"
    assert reporter_trust("P1", "witnessed", T0, 0, 0).score == pytest.approx(0.95)
    with pytest.raises(ValueError):
        reporter_trust("P1", "bogus", T0, 0, 0)


def test_risk_interval_and_determinism():
    early = score_risk("P1", T0, adh_alpha=9.5, adh_beta=1.5)
    late = score_risk("P1", T0, adh_alpha=60, adh_beta=40, refill_gap_days=10, weekday_flag=True)
    assert early.ci_low <= early.p <= early.ci_high
    assert late.p > early.p and late.drivers[0][1] > 0
    wide = score_risk("P1", T0, adh_alpha=5, adh_beta=5)
    narrow = score_risk("P1", T0, adh_alpha=500, adh_beta=500)
    assert wide.ci_high - wide.ci_low > narrow.ci_high - narrow.ci_low
    assert early == score_risk("P1", T0, adh_alpha=9.5, adh_beta=1.5)


def test_lifecycle():
    b = BeliefState("hypothesis", 0, 0)
    assert advance_belief_state(b, 5, 0.95, confirm_met=True).state == "confirmed"
    c = BeliefState("confirmed", 0, 10)
    d = advance_belief_state(c, 31, 0.9, confirm_met=True)
    assert d.state == "dormant"
    assert advance_belief_state(d, 52, 0.9, confirm_met=True).state == "retired"
    assert (
        advance_belief_state(d, 33, 0.9, confirm_met=True, supported_today=True).state
        == "confirmed"
    )
    assert (
        advance_belief_state(b, 3, 0.5, confirm_met=False, doctor_reject=True).retired_reason
        == "doctor_reject"
    )
    assert advance_belief_state(b, 43, 0.5, confirm_met=False).state == "retired"
