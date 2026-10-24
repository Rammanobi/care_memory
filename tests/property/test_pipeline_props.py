"""Pipeline properties: same input twice gives same output; the future never leaks into as_of."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cm.memory.pipeline import compute_memory

PID = UUID("22222222-2222-2222-2222-222222222222")
T0 = datetime(2026, 1, 5, 12, tzinfo=UTC)
S = settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def build(statuses):
    return [
        {
            "event_id": UUID(int=i + 1),
            "type": "DoseCheckin",
            "occurred_at": T0 + timedelta(days=i),
            "recorded_at": T0 + timedelta(days=i),
            "payload": {"status": s},
            "source": "telegram",
            "supersedes": None,
            "reporter_mode": "self",
        }
        for i, s in enumerate(statuses)
    ]


statuses = st.lists(st.sampled_from(["taken", "missed"]), min_size=5, max_size=60)


@S
@given(statuses)
def test_same_input_twice_same_output(sts):
    evs = build(sts)
    as_of = T0 + timedelta(days=len(sts), hours=1)
    kw = {"treatment_start": T0.date()}
    assert compute_memory(PID, evs, as_of, {}, **kw) == compute_memory(
        PID, list(reversed(evs)), as_of, {}, **kw
    )


@S
@given(statuses, st.lists(st.sampled_from(["taken", "missed"]), min_size=1, max_size=20))
def test_no_future_leakage(sts, extra):
    base = build(sts)
    as_of = T0 + timedelta(days=len(sts) - 1, hours=1)
    future = [
        {
            **e,
            "event_id": uuid4(),
            "occurred_at": as_of + timedelta(days=i + 1),
            "recorded_at": as_of + timedelta(days=i + 1),
        }
        for i, e in enumerate(build(extra))
    ]
    late_record = [
        {
            **base[-1],
            "event_id": uuid4(),
            "payload": {"status": "missed"},
            "recorded_at": as_of + timedelta(days=3),
        }
    ]  # occurred before, recorded after
    kw = {"treatment_start": T0.date()}
    clean = compute_memory(PID, base, as_of, {}, **kw)
    assert clean == compute_memory(PID, base + future + late_record, as_of, {}, **kw)
