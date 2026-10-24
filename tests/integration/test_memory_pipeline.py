"""Memory pipeline against the caremem_test database only (the root conftest forces DB_NAME)."""

from datetime import timedelta

import pytest

from cm.core import clock
from cm.core.db import transaction
from cm.jobs.nightly import _memory_summary
from cm.memory.nightly import run_nightly
from cm.memory.pipeline import run_patient
from cm.store import ai_repo, events_repo, memory_repo

pytestmark = pytest.mark.usefixtures("pinned_clock")


def _rows(pid, today):
    with transaction() as c:
        return (
            memory_repo.get_features(pid, today, conn=c),
            memory_repo.get_risk(pid, today, conn=c),
            [dict(b) for b in memory_repo.beliefs_as_of(pid, today, conn=c)],
            [dict(r) for r in memory_repo.stored_conflicts(pid, conn=c)],
        )


def test_pipeline_idempotent_and_persists():
    with transaction() as c:
        pid, _ = ai_repo.resolve_patient("PT-0142", conn=c)
        day0, _ = ai_repo.sim_day0(conn=c)
    first = run_patient(pid, clock.now(), day0=day0)
    assert first is not None
    snap1 = _rows(pid, first.as_of)
    again = run_patient(pid, clock.now(), day0=day0)
    assert again == first
    assert _rows(pid, first.as_of) == snap1
    feats, risk, beliefs, conflicts = snap1
    assert feats is not None and feats["engine_version"] == "memory_v1"
    assert risk is not None and risk["ci_low"] <= risk["ci_high"]
    assert len(beliefs) == len(first.beliefs)
    assert len(conflicts) == len(first.conflicts)
    assert _memory_summary(first)["as_of"] == first.as_of.isoformat()


def test_pipeline_no_future_leakage_in_db():
    with transaction() as c:
        pid, _ = ai_repo.resolve_patient("PT-0142", conn=c)
    early = clock.now() - timedelta(days=20)
    r_early = run_patient(pid, early, persist=False)
    visible = events_repo.query(pid, early)
    assert r_early is not None and all(e["occurred_at"] <= early for e in visible)
    assert r_early.as_of < clock.now().date()


def test_run_nightly_all_patients_idempotent():
    a = run_nightly(clock.now())
    b = run_nightly(clock.now())
    assert a == b and a["computed"] >= 1
