"""Property tests for cm/memory: stats intervals, risk, trust, weekday, lifecycle, features, refill.

Bounds in [0, 1], the interval contains the point estimate, determinism, shuffle invariance and no
future leakage (events recorded after as_of never change a number).
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from cm.core.clock import ist_date
from cm.memory.detectors.refill import refill_coverage
from cm.memory.detectors.trust import PRIORS, reporter_trust
from cm.memory.detectors.weekday import weekday_effect
from cm.memory.features import compute_features
from cm.memory.lifecycle import BeliefState, advance_belief_state
from cm.memory.risk import score_risk
from cm.memory.stats import beta_interval, percentile

PROPS = settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
FEW = settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
T0 = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
ab = st.floats(min_value=1.0, max_value=300.0, allow_nan=False)


# ----------------------------------------------------------------------------- stats
@PROPS
@given(st.lists(st.floats(-1e6, 1e6, allow_nan=False), min_size=1, max_size=50),
       st.floats(0, 1), st.floats(0, 1))  # fmt: skip
def test_percentile_bounded_and_monotone(xs: list[float], q1: float, q2: float) -> None:
    s = sorted(xs)
    lo, hi = sorted((q1, q2))
    a, b = percentile(s, lo), percentile(s, hi)
    assert s[0] - 1e-6 <= a <= b + 1e-6 <= s[-1] + 2e-6


@FEW
@given(ab, ab, st.text(max_size=8))
def test_beta_interval_bounds_and_contains_mean(a: float, b: float, key: str) -> None:
    mean, lo, hi = beta_interval(a, b, (key,), draws=800)
    assert 0 <= lo <= hi <= 1
    assert lo <= mean <= hi
    assert beta_interval(a, b, (key,), draws=800) == (mean, lo, hi)  # seeded


# ----------------------------------------------------------------------------- risk
@FEW
@given(ab, ab, st.integers(-5, 60), st.integers(-5, 20), st.booleans(), st.text(max_size=6))
def test_risk_bounds_interval_and_determinism(
    a: float, b: float, gap: int, un: int, wd: bool, pid: str
) -> None:
    r = score_risk(pid, date(2026, 2, 1), adh_alpha=a, adh_beta=b, refill_gap_days=gap,
                   consecutive_unanswered=un, weekday_flag=wd)  # fmt: skip
    assert 0 <= r.ci_low <= r.p <= r.ci_high <= 1
    assert r == score_risk(pid, date(2026, 2, 1), adh_alpha=a, adh_beta=b, refill_gap_days=gap,
                           consecutive_unanswered=un, weekday_flag=wd)  # fmt: skip
    assert all(v > 0 for _, v in r.drivers) and len(r.drivers) <= 3


@FEW
@given(ab, ab, st.integers(0, 30))
def test_risk_monotone_in_refill_gap(a: float, b: float, gap: int) -> None:
    lo = score_risk("p", "d", adh_alpha=a, adh_beta=b, refill_gap_days=gap)
    hi = score_risk("p", "d", adh_alpha=a, adh_beta=b, refill_gap_days=gap + 5)
    assert hi.p >= lo.p


# ----------------------------------------------------------------------------- trust / weekday
@FEW
@given(st.sampled_from(sorted(PRIORS)), st.integers(0, 60), st.integers(0, 60))
def test_trust_bounds(mode: str, agree: int, disagree: int) -> None:
    t = reporter_trust("p", mode, "2026-01-01", agree, disagree)
    assert 0 <= t.ci_low <= t.score <= t.ci_high <= 1
    assert t.n == agree + disagree
    if t.state == "confirmed":
        assert t.n >= 10 and t.ci_high - t.ci_low <= 0.35


@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.integers(0, 10), st.integers(0, 10), st.integers(0, 40), st.integers(0, 40))
def test_weekday_belief_bounds(m: int, extra: int, rm: int, rextra: int) -> None:
    w = weekday_effect("p", "Thursday", "2026-01-01", m, m + extra, rm, rm + rextra)
    assert 0 <= w.posterior <= 1
    assert -1 <= w.ci_low <= w.effect <= w.ci_high <= 1
    if w.state == "confirmed":
        assert m >= 4 and w.posterior >= 0.9


# ----------------------------------------------------------------------------- lifecycle
steps = st.lists(st.tuples(st.floats(0, 1), st.booleans(), st.booleans(), st.booleans()), max_size=90)


@PROPS
@given(steps)
def test_lifecycle_transitions_are_legal(seq: list) -> None:
    legal = {
        "hypothesis": {"hypothesis", "confirmed", "retired"},
        "confirmed": {"confirmed", "dormant", "retired"},
        "dormant": {"dormant", "confirmed", "retired"},
        "retired": {"retired"},
    }
    b = BeliefState("hypothesis", 0, 0)
    for day, (post, confirm, support, reject) in enumerate(seq, start=1):
        nb = advance_belief_state(b, day, post, confirm_met=confirm, supported_today=support,
                                  doctor_reject=reject and day % 17 == 0)  # fmt: skip
        assert nb.state in legal[b.state], (b.state, nb.state)
        assert nb.last_support_day <= day
        if nb.state == "retired":
            assert nb.retired_reason
        b = nb


# ----------------------------------------------------------------------------- features / refill
@st.composite
def event_lists(draw: Any) -> list[dict[str, Any]]:
    out = []
    for i in range(draw(st.integers(0, 40))):
        occ = T0 + timedelta(minutes=draw(st.integers(0, 60 * 24 * 40)))
        rec = occ + timedelta(minutes=draw(st.sampled_from([0, 0, 30, 60 * 24, 60 * 24 * 5])))
        kind = draw(st.sampled_from(["DoseCheckin", "DoseCheckin", "Dispense", "ContextNote"]))
        if kind == "DoseCheckin":
            payload: dict[str, Any] = {"status": draw(st.sampled_from(["taken", "missed", "undone"]))}
        elif kind == "Dispense":
            payload = {"days_supply": draw(st.sampled_from([7, 14, 30]))}
        else:
            payload = {"kind": "note"}
        out.append({"event_id": UUID(int=i + 1), "type": kind, "occurred_at": occ, "recorded_at": rec,
                    "payload": payload, "source": "telegram", "supersedes": None})  # fmt: skip
    return out


as_ofs = st.integers(0, 60 * 24 * 45).map(lambda m: T0 + timedelta(minutes=m))


@PROPS
@given(event_lists(), as_ofs, st.integers(0, 2**31))
def test_features_shuffle_invariant(evs: list, as_of: datetime, seed: int) -> None:
    base = compute_features(evs, as_of).as_dict()
    sh = evs[:]
    random.Random(seed).shuffle(sh)  # noqa: S311
    assert compute_features(sh, as_of).as_dict() == base


@PROPS
@given(event_lists(), as_ofs, st.integers(1, 60 * 24 * 10))
def test_features_no_future_leakage(evs: list, as_of: datetime, later: int) -> None:
    base = compute_features(evs, as_of).as_dict()
    fut = [
        {**e, "event_id": UUID(int=10_000 + i), "recorded_at": as_of + timedelta(minutes=later)}
        for i, e in enumerate(evs)
    ]
    assert compute_features(evs + fut, as_of).as_dict() == base
    f = compute_features(evs, as_of)
    assert min(f.numbers.values(), default=0) >= 0
    assert f.missed_3d <= f.missed_7d <= 7 and f.taken_7d <= 7


@PROPS
@given(event_lists(), as_ofs)
def test_refill_detector_agrees_with_features_on_ist_days(evs: list, as_of: datetime) -> None:
    """Both refill paths must count gap days on IST calendar dates (clock rule)."""
    rc = refill_coverage(evs, as_of)
    assert rc.gap_days == compute_features(evs, as_of).refill_gap_days
    if rc.supply_end is not None:
        assert rc.gap_days == max(0, (ist_date(as_of) - rc.supply_end).days)


@PROPS
@given(event_lists(), as_ofs, st.integers(1, 60 * 24 * 10))
def test_refill_no_future_leakage(evs: list, as_of: datetime, later: int) -> None:
    fut = [{**e, "recorded_at": as_of + timedelta(minutes=later)} for e in evs]
    assume(evs)
    assert refill_coverage(evs + fut, as_of).gap_days == refill_coverage(evs, as_of).gap_days
