"""cm.core: clock pinning, ids and idempotency keys (no database)."""

from datetime import UTC, date, datetime

import pytest

from cm.core import clock
from cm.core.ids import det_id, idempotency_key


def test_clock_global_and_per_clinic_pin() -> None:
    clock.unpin()
    real = clock.now()
    a = datetime(2026, 1, 1, tzinfo=UTC)
    b = datetime(2026, 2, 2, tzinfo=UTC)
    clock.pin(a)
    clock.pin(b, clinic_id="c1")
    try:
        assert clock.now() == a
        assert clock.now("c1") == b
        assert clock.now("other") == a
    finally:
        clock.unpin()
        clock.unpin("c1")
    assert clock.now() >= real


def test_sim_instant_is_18_ist() -> None:
    at = clock.sim_instant(date(2026, 8, 27), 59)
    assert at.astimezone(clock.IST).isoformat().startswith("2026-10-25T18:00")


def test_ids_are_deterministic_and_keys_validated() -> None:
    assert det_id("a", "b") == det_id("a", "b")
    assert det_id("a", "b") != det_id("a", "c")
    assert idempotency_key("web", "dose", "1") == "web:dose:1"
    with pytest.raises(ValueError):
        idempotency_key("x" * 300)
