"""R6 household contact screening (P0, M8)."""

from __future__ import annotations

from uuid import uuid4

from cm.contracts.admin import RuleThresholds
from cm.rules import rules_r6

from .builders import PATIENT, TH, d, ev, regimen
from .builders import contact as hh


def test_r6_silent_before_due_day() -> None:
    assert rules_r6.evaluate([regimen(0)], PATIENT, d(13), TH) == []


def test_r6_zero_listed_contacts_fires_at_due_day() -> None:
    start = regimen(0)
    out = rules_r6.evaluate([start], PATIENT, d(14), TH)
    assert len(out) == 1
    c = out[0]
    assert (
        c.rule == "R6" and c.tier == "amber" and c.opened_as_of == d(14) and c.closed_as_of is None
    )
    assert c.title == "No household contacts listed by treatment day 14."
    assert c.evidence_ids == [f"E:{start['event_id']}"]  # anchored on the treatment-start record


def test_r6_unscreened_contact_fires_and_closes_when_all_screened() -> None:
    a, b = uuid4(), uuid4()
    rows = [
        regimen(0),
        hh(3, a, "listed", relation="spouse", age_band="15-59"),
        hh(3, b, "listed", relation="child", age_band="<5"),
        hh(5, a, "screened"),
    ]
    out = rules_r6.evaluate(rows, PATIENT, d(20), TH)
    assert (
        out[0].title == "1 of 2 household contacts not screened (due day 14)."
        and out[0].closed_as_of is None
    )
    done = rows + [hh(22, b, "flagged")]
    closed = rules_r6.evaluate(done, PATIENT, d(30), TH)
    assert closed[0].closed_as_of == d(22) and closed[0].opened_as_of == d(14)
    assert closed[0].conflict_id == out[0].conflict_id


def test_r6_all_screened_before_due_never_opens() -> None:
    a = uuid4()
    rows = [regimen(0), hh(2, a, "listed"), hh(4, a, "screened")]
    assert rules_r6.evaluate(rows, PATIENT, d(40), TH) == []


def test_r6_suppressed_by_household_declined_note() -> None:
    note = ev("ContextNote", 2, rmode="told", origin="supporter_text", kind="household_declined")
    assert rules_r6.evaluate([regimen(0), note], PATIENT, d(30), TH) == []
    late_note = ev(
        "ContextNote", 20, rmode="told", origin="supporter_text", kind="household_declined"
    )
    out = rules_r6.evaluate([regimen(0), late_note], PATIENT, d(30), TH)
    assert out[0].closed_as_of == d(20) and "declined" in out[0].title


def test_r6_uses_recorded_date_for_screening() -> None:
    a = uuid4()
    rows = [
        regimen(0),
        hh(2, a, "listed"),
        hh(10, a, "screened", rec=18),
    ]  # screening keyed in late
    out = rules_r6.evaluate(rows, PATIENT, d(25), TH)
    assert out[0].opened_as_of == d(14) and out[0].closed_as_of == d(18)


def test_r6_due_day_comes_from_thresholds() -> None:
    th = RuleThresholds(contacts_due_day=21)
    assert rules_r6.evaluate([regimen(0)], PATIENT, d(20), th) == []
    assert rules_r6.evaluate([regimen(0)], PATIENT, d(21), th)[0].title.endswith("day 21.")


def test_r6_reopens_when_a_new_contact_is_listed() -> None:
    a, b = uuid4(), uuid4()
    rows = [regimen(0), hh(2, a, "listed"), hh(16, a, "screened"), hh(25, b, "listed")]
    out = rules_r6.evaluate(rows, PATIENT, d(30), TH)
    assert out[0].opened_as_of == d(14) and out[0].closed_as_of is None


def test_r6_never_names_contacts() -> None:
    a = uuid4()
    rows = [regimen(0), hh(2, a, "listed", note="Sunitha lives upstairs")]
    out = rules_r6.evaluate(rows, PATIENT, d(20), TH)
    assert "Sunitha" not in out[0].model_dump_json()
