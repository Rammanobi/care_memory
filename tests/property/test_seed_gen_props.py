"""Seed determinism for the pure simulator: same (seed, patients, days) -> identical cohort; prefixes
are stable when the cohort grows; reported values never invent a dose after the visible course."""

from __future__ import annotations

from dataclasses import asdict

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cm.sim.gen import LABEL_HORIZON, generate_patients

PROPS = settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@PROPS
@given(st.integers(0, 2**32), st.integers(0, 12), st.integers(1, 90))
def test_same_seed_same_cohort(seed: int, n: int, days: int) -> None:
    a = [asdict(p) for p in generate_patients(seed, n, days)]
    assert a == [asdict(p) for p in generate_patients(seed, n, days)]
    assert len(a) == n
    for p in a:
        assert len(p["taken"]) == days + LABEL_HORIZON == len(p["reported"])
        assert all(r is None for r in p["reported"][days:])
        assert 0 < p["base_rate"] < 1


@PROPS
@given(st.integers(0, 2**32), st.integers(1, 8), st.integers(1, 6), st.integers(5, 60))
def test_growing_cohort_keeps_existing_patients(seed: int, n: int, extra: int, days: int) -> None:
    small = [asdict(p) for p in generate_patients(seed, n, days)]
    big = [asdict(p) for p in generate_patients(seed, n + extra, days)]
    assert big[:n] == small


@PROPS
@given(st.integers(0, 2**31), st.integers(5, 40))
def test_different_seeds_differ(seed: int, days: int) -> None:
    a = [p.taken for p in generate_patients(seed, 5, days)]
    b = [p.taken for p in generate_patients(seed + 1, 5, days)]
    assert a != b
