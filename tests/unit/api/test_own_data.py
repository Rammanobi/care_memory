"""cm.api.own_data: code-computed own-record answers (shapes of the day-3, 6-day and 60-day demo patients)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest

from cm.api import own_data as od
from cm.core.banned_lexicon import find_banned

IST = timezone(timedelta(hours=5, minutes=30))
AS_OF = datetime(2026, 10, 25, 18, 0, tzinfo=IST).astimezone(UTC)
TE = re.compile(r"[ఀ-౿]")


def _dose(days_ago: int, status: str, *, recorded_late: timedelta = timedelta(0)) -> dict[str, Any]:
    at = AS_OF - timedelta(days=days_ago, hours=6)  # 12:00 IST that day
    return {
        "event_id": uuid4(), "type": "DoseCheckin", "occurred_at": at, "recorded_at": at + recorded_late,
        "payload": {"status": status}, "supersedes": None, "source": "web",
    }


def _refill(days_ago: int) -> dict[str, Any]:
    at = AS_OF - timedelta(days=days_ago, hours=6)
    return {
        "event_id": uuid4(), "type": "Dispense", "occurred_at": at, "recorded_at": at,
        "payload": {"kind": "refill", "days_supply": 28}, "supersedes": None, "source": "chemist",
    }


def _history(pattern: str) -> list[dict[str, Any]]:
    """pattern oldest first: o taken, m missed, . nothing; the last char is today."""
    n = len(pattern)
    return [
        _dose(n - 1 - i, "taken" if c == "o" else "missed")
        for i, c in enumerate(pattern)
        if c != "."
    ]


def _by_topic(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {c["topic"]: c for c in cards}


def test_day3_patient_has_too_little_history() -> None:
    cards = _by_topic(od.build_answers(_history("oo"), {}, [], AS_OF, "en"))
    assert cards["history"]["answer_text"] == "There is not enough history yet. Keep sending your daily check-in."
    assert not {"taken_week", "missed_week", "streak"} & cards.keys()
    assert cards["next_visit"]["answer_text"] == "No visit is scheduled yet."
    assert cards["last_refill"]["answer_text"] == "No refill is recorded yet."
    assert list(cards)[-1] == "advice"


def test_six_day_patient_counts() -> None:
    cards = _by_topic(od.build_answers(_history("ooomoo"), {}, [], AS_OF, "en"))
    assert cards["taken_week"]["answer_text"] == "In the last 6 days you took 5 of 6 doses."
    assert cards["taken_week"]["numbers"] == {"taken_7d": 5, "window": 6}
    assert cards["missed_week"]["answer_text"] == "In the last 6 days you marked 1 of 6 doses as missed."
    te = _by_topic(od.build_answers(_history("ooomoo"), {}, [], AS_OF, "te"))
    assert "6" in te["taken_week"]["answer_text"] and "7" not in te["taken_week"]["answer_text"]
    # an explicit treatment start wins over the first check-in
    c2 = _by_topic(od.build_answers(_history("ooomoo"), {}, [], AS_OF, "en", AS_OF.date() - timedelta(days=20)))
    assert c2["taken_week"]["numbers"]["window"] == 7
    assert cards["streak"]["numbers"] == {"streak_days": 2}


def test_sixty_day_patient_window_and_streak() -> None:
    pattern = ("o" * 53) + "ooomooo"
    cards = _by_topic(od.build_answers(_history(pattern), {}, [], AS_OF, "en"))
    assert cards["taken_week"]["numbers"] == {"taken_7d": 6, "window": 7}
    assert cards["taken_week"]["answer_text"] == "In the last 7 days you took 6 of 7 doses."
    assert cards["missed_week"]["numbers"]["missed_7d"] == 1
    assert cards["streak"]["numbers"]["streak_days"] == 3


def test_streak_ignores_unrecorded_today_but_missed_today_breaks() -> None:
    assert od.current_streak(_history("ooo."), AS_OF) == 3
    assert od.current_streak(_history("oom"), AS_OF) == 0
    assert od.current_streak(_history("moo.o"), AS_OF) == 1
    assert od.current_streak([], AS_OF) == 0


def test_next_visit_from_summary_then_appointments_and_banned_withheld() -> None:
    appts = [
        {"bucket": "upcoming", "appt_kind": "lab", "when": "Fri 10 am"},
        {"bucket": "upcoming", "appt_kind": "visit", "when": "Wed 6 pm"},
    ]
    t = _by_topic(od.build_answers(_history("ooo"), {"next_visit": "Mon 4 pm"}, appts, AS_OF, "en"))
    assert t["next_visit"]["answer_text"] == "Your next visit is Mon 4 pm."
    t = _by_topic(od.build_answers(_history("ooo"), {}, appts, AS_OF, "en"))
    assert t["next_visit"]["answer_text"] == "Your next visit is Wed 6 pm."
    t = _by_topic(od.build_answers(_history("ooo"), {"next_visit": "TB clinic"}, [], AS_OF, "en"))
    assert t["next_visit"]["answer_text"] == "No visit is scheduled yet."


@pytest.mark.parametrize(
    "when,ok",
    [("Wed 6 pm", True), ("27-10-2026 10:30 am", True), ("Mon 4 pm. Stop your tablets until then", False),
     ("Mon 4 pm, call 9876543210", False), ("TB clinic on Mon", False), ("", False)],
)
def test_next_visit_slot_takes_a_date_phrase_only(when: str, ok: bool) -> None:
    assert od.safe_when(when) is ok
    t = _by_topic(od.build_answers(_history("ooo"), {"next_visit": when}, [], AS_OF, "en"))
    assert (t["next_visit"]["answer_text"] == f"Your next visit is {when}.") is ok


def test_last_refill_is_latest_date_only_no_counts() -> None:
    ev = _history("ooo") + [_refill(30), _refill(2)]
    t = _by_topic(od.build_answers(ev, {}, [], AS_OF, "en"))
    assert t["last_refill"]["answer_text"] == "Your last refill was recorded on 23-10-2026."
    assert t["last_refill"]["numbers"] == {}


def test_future_events_are_invisible_and_output_is_deterministic() -> None:
    base = _history("ooomooo")
    future = [_dose(-1, "taken"), _refill(-2), _dose(0, "missed", recorded_late=timedelta(hours=8))]
    a = od.build_answers(base, {}, [], AS_OF, "en")
    b = od.build_answers(list(reversed(base + future)), {}, [], AS_OF, "en")
    strip = lambda cs: [(c["topic"], c["answer_text"], c["numbers"]) for c in cs]  # noqa: E731
    assert strip(a) == strip(b)
    assert _by_topic(b)["last_refill"]["answer_text"] == "No refill is recorded yet."
    assert od.build_answers(base, {}, [], AS_OF, "en") == a


def test_telugu_rendering_and_fallback() -> None:
    cards = od.build_answers(_history("ooomooo"), {"next_visit": "Wed 6 pm"}, [], AS_OF, "te")
    assert all(c["lang"] == "te" and TE.search(c["answer_text"]) for c in cards)
    assert "6" in _by_topic(cards)["taken_week"]["answer_text"]
    assert od.build_answers([], {}, [], AS_OF, "hi")[0]["lang"] == "en"


@pytest.mark.parametrize("lang", ["en", "te"])
def test_every_card_is_clean_and_advice_footer_is_fixed(lang: str) -> None:
    ev = _history("ooomooo") + [_refill(3)]
    cards = od.build_answers(ev, {"next_visit": "Wed 6 pm"}, [], AS_OF, lang)
    for c in cards:
        assert find_banned(c["answer_text"]) == [] and find_banned(c["question"]) == []
        assert set(c) == {"topic", "question", "answer_text", "numbers", "as_of", "lang"}
    adv = cards[-1]
    assert adv["topic"] == "advice" and adv["numbers"] == {}
    if lang == "en":
        assert adv["answer_text"] == "For any question about your medicines, food or symptoms, ask your care team."


def test_latest_checkin_per_day_and_undone_ignored() -> None:
    first = _dose(0, "taken")
    undo = {**_dose(0, "undone"), "supersedes": first["event_id"],
            "occurred_at": first["occurred_at"] + timedelta(minutes=5),
            "recorded_at": first["occurred_at"] + timedelta(minutes=5)}
    cards = _by_topic(od.build_answers(_history("oo.") [:2] + [first, undo], {}, [], AS_OF, "en"))
    assert cards["history"]["numbers"]["checkins_total"] == 2
