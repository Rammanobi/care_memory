from datetime import date

from cm.memory.features import compute_features
from tests.unit.ai.conftest import AS_OF, ev


def test_numbers(events):
    f = compute_features(events, AS_OF, day0=date(2026, 8, 27))
    assert (f.missed_3d, f.missed_7d) == (1, 2)
    assert f.longest_streak == 6  # 14..9 days ago
    assert f.refill_gap_days == 11  # ran out day 47 (Oct 13), today Oct 24
    assert f.quiet_days == 0
    assert f.conflicts and f.conflicts[0]["kind"] == "self_report_vs_refill"
    assert f.cites["missed_7d"] and f.cites["refill_gap_days"]


def test_as_of_respected(events):
    future = ev("DoseCheckin", -2, {"status": "missed"})
    assert compute_features([*events, future], AS_OF).missed_3d == 1


def test_undone_and_superseded_ignored(events):
    marked = ev("DoseCheckin", 0, {"status": "missed"})
    undo = ev("DoseCheckin", 0, {"status": "undone"}, supersedes=marked["event_id"])
    assert compute_features([*events, marked, undo], AS_OF).missed_3d == 1


def test_weekday_pattern():
    evs = [ev("DoseCheckin", d, {"status": "missed"}) for d in (7, 14)] + [ev("DoseCheckin", 1, {"status": "taken"})]
    assert compute_features(evs, AS_OF).top_miss_weekday == "Saturday"
