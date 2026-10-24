"""Usage-by-task aggregation: duplicate display names merge, order is stable, totals stay exact."""

from cm.api.routers.admin import _merge_tasks


def _rows() -> list[dict[str, object]]:
    return [
        {"task_type": "ingest_event", "cost": 10.005},
        {"task_type": "seed", "cost": 20.0},
        {"task_type": "nightly", "cost": 24.485},
    ]


def test_duplicate_other_rows_merge_and_totals_are_exact() -> None:
    out = _merge_tasks(_rows(), 54.49)
    names = [t.name for t in out]
    assert names.count("Other") == 1 and len(names) == 2
    assert [t.name for t in out] == ["Other", "Nightly memory rebuild"]
    assert out[0].spend == 30.01 and out[1].spend == 24.48  # rounded once, after merging
    assert abs(sum(t.spend for t in out) - 54.49) < 0.011  # no 54.49 -> 54.4 truncation


def test_order_is_deterministic_for_any_input_order() -> None:
    a = _merge_tasks(_rows(), 54.49)
    b = _merge_tasks(list(reversed(_rows())), 54.49)
    assert a == b


def test_zero_spend_has_zero_pct() -> None:
    assert _merge_tasks([{"task_type": "nightly", "cost": 0.0}], 0.0)[0].pct == 0
