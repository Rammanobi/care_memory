"""Portal fields are never invented: relation and next visit come from the clinic's record or are None."""

from cm.api.routers.portal import _appt_visible, _relation, _time_of


def test_relation_is_recorded_value_or_none() -> None:
    assert _relation({"supporter_relation": "sister"}) == "sister"
    assert _relation({}) is None
    assert _relation({"supporter_relation": "  "}) is None
    assert _relation({"supporter_relation": None}) is None
    assert _relation({"supporter_relation": 7}) is None


def test_relation_with_banned_word_is_withheld() -> None:
    assert _relation({"supporter_relation": "TB buddy"}) is None


def test_no_reminder_request_means_no_time() -> None:
    assert _time_of(None) is None


def test_appointment_with_banned_word_is_withheld() -> None:
    ok = {"title": "Clinic visit", "when": "Wed 6 pm", "place": "Anantapur Clinic", "note": None}
    assert _appt_visible(ok)
    assert not _appt_visible({**ok, "note": "Bring your TB card"})
