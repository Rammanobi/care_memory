"""R1-R5: positive, negative and edge cases per rule (02 F6 tests)."""

from __future__ import annotations

import pandas as pd

from cm.rules import rules_r1, rules_r2, rules_r3, rules_r4, rules_r5

from .builders import PATIENT, TH, d, dispense, ev, prompt, regimen, taken, visit

# --------------------------------------------------------------------- R1


def _ravi_refill(closing_day: int = 44, closing_rec: int | None = None) -> list[dict]:
    rows = [regimen(0), dispense(0)] + [taken(i) for i in range(0, 60)]
    rows.append(dispense(closing_day, closing_rec))
    return rows


def test_r1_opens_on_gap_and_closes_on_dispense() -> None:
    rows = _ravi_refill()
    mid = rules_r1.evaluate(rows, PATIENT, d(40), TH)
    assert len(mid) == 1 and mid[0].tier == "amber" and mid[0].closed_as_of is None
    assert mid[0].opened_as_of == d(33)  # gap from day 30 + 3-day chemist lag
    late = rules_r1.evaluate(rows, PATIENT, d(60), TH)
    assert len(late) == 1 and late[0].closed_as_of == d(44)
    assert late[0].conflict_id == mid[0].conflict_id
    assert late[0].title == "Refill due day 30, bought day 44; 14 'Taken' reports in between."
    assert all(ref.startswith("E:") for ref in late[0].evidence_ids)


def test_r1_dispense_recorded_two_days_late_does_not_fire() -> None:
    rows = [regimen(0), dispense(0)] + [taken(i) for i in range(0, 50)] + [dispense(30, rec=32)]
    for day in (31, 32, 33, 40, 49):
        assert rules_r1.evaluate(rows, PATIENT, d(day), TH) == []


def test_r1_late_record_beyond_lag_opens_then_closes_on_record_day() -> None:
    rows = [regimen(0), dispense(0)] + [taken(i) for i in range(0, 50)] + [dispense(30, rec=36)]
    assert rules_r1.evaluate(rows, PATIENT, d(35), TH)[0].closed_as_of is None
    assert rules_r1.evaluate(rows, PATIENT, d(45), TH)[0].closed_as_of == d(36)


def test_r1_needs_three_self_taken_days_and_a_dispense() -> None:
    few = [regimen(0), dispense(0)] + [taken(i) for i in range(0, 32)]
    assert rules_r1.evaluate(few, PATIENT, d(40), TH) == []  # only days 30, 31 in the gap
    witnessed = [regimen(0), dispense(0)] + [taken(i, mode="witnessed") for i in range(0, 50)]
    assert rules_r1.evaluate(witnessed, PATIENT, d(45), TH) == []
    missed = [regimen(0), dispense(0)] + [taken(i, status="missed") for i in range(0, 50)]
    assert rules_r1.evaluate(missed, PATIENT, d(45), TH) == []
    no_chemist = [regimen(0)] + [taken(i) for i in range(0, 50)]
    assert rules_r1.evaluate(no_chemist, PATIENT, d(45), TH) == []


def test_r1_ledger_without_days_supply_uses_dose_from_tablets() -> None:
    rows = [
        regimen(0),
        dispense(0, tablets=120, days_supply=30),
        dispense(30, tablets=40, days_supply=None),
    ]
    rows += [taken(i) for i in range(0, 60)]
    out = rules_r1.evaluate(rows, PATIENT, d(50), TH)
    assert len(out) == 1 and "Refill due day 40" in out[0].title  # 120/4 + 40/4 = 40 days


# --------------------------------------------------------------------- R2


def test_r2_red_when_resistant_on_first_line_closes_on_switch() -> None:
    lab = ev(
        "LabResult",
        20,
        source="lab",
        test="cbnaat",
        result="mtb_detected",
        rif_resistant=True,
        report_date=d(20).isoformat(),
    )
    rows = [regimen(0), lab]
    out = rules_r2.evaluate(rows, PATIENT, d(25), TH)
    assert len(out) == 1 and out[0].tier == "red" and out[0].opened_as_of == d(20)
    assert f"E:{lab['event_id']}" in out[0].evidence_ids
    switched = rows + [regimen(23, line="second")]
    assert rules_r2.evaluate(switched, PATIENT, d(25), TH)[0].closed_as_of == d(23)


def test_r2_negative_cases() -> None:
    sens = ev(
        "LabResult",
        20,
        test="cbnaat",
        result="mtb_detected",
        rif_resistant=False,
        report_date=d(20).isoformat(),
    )
    assert rules_r2.evaluate([regimen(0), sens], PATIENT, d(25), TH) == []
    res = ev(
        "LabResult",
        20,
        test="cbnaat",
        result="mtb_detected",
        rif_resistant=True,
        report_date=d(20).isoformat(),
    )
    assert rules_r2.evaluate([regimen(0, line="second"), res], PATIENT, d(25), TH) == []


def test_r2_no_regimen_record_fails_safe() -> None:
    res = ev(
        "LabResult",
        5,
        test="cbnaat",
        result="mtb_detected",
        rif_resistant=True,
        report_date=d(5).isoformat(),
    )
    assert len(rules_r2.evaluate([res], PATIENT, d(6), TH)) == 1


# --------------------------------------------------------------------- R3


def _paid(day: int, month: str = "2026-01") -> dict:
    return ev(
        "PortalPayment",
        day,
        source="portal",
        nikshay_id="NK1",
        month=month,
        amount=1000,
        status="paid",
        paid_on=d(day).isoformat(),
    )


def _report(day: int, status: str, month: str = "2026-01") -> dict:
    return ev("PaymentReport", day, rmode="self", source="telegram", month=month, status=status)


def test_r3_paid_but_not_received_for_30_days() -> None:
    rows = [_paid(10), _report(15, "not_received"), _report(35, "not_received")]
    assert rules_r3.evaluate(rows, PATIENT, d(39), TH) == []
    out = rules_r3.evaluate(rows, PATIENT, d(40), TH)
    assert len(out) == 1 and out[0].opened_as_of == d(40) and out[0].tier == "amber"
    closed = rules_r3.evaluate(rows + [_report(70, "received")], PATIENT, d(80), TH)
    assert closed[0].closed_as_of == d(70)


def test_r3_resolved_within_30_days_never_fires() -> None:
    rows = [_paid(10), _report(15, "not_received"), _report(20, "received")]
    assert rules_r3.evaluate(rows, PATIENT, d(60), TH) == []


def test_r3_unpaid_more_than_60_days() -> None:
    pend = ev(
        "PortalPayment",
        5,
        source="portal",
        nikshay_id="NK1",
        month="2026-01",
        amount=1000,
        status="pending",
    )
    assert rules_r3.evaluate([pend], PATIENT, d(65), TH) == []
    out = rules_r3.evaluate([pend], PATIENT, d(66), TH)
    assert len(out) == 1 and "not paid 60+ days" in out[0].title
    assert rules_r3.evaluate([pend, _paid(50)], PATIENT, d(80), TH) == []


# --------------------------------------------------------------------- R4


def test_r4_danger_by_flag_code_or_index() -> None:
    by_idx = ev("SymptomReport", 3, rmode="self", items=[6], codes=[], danger=False)
    by_code = ev("SymptomReport", 4, rmode="self", items=[], codes=["chest_pain"], danger=False)
    by_flag = ev("SymptomReport", 5, rmode="self", items=[], codes=[], danger=True)
    benign = ev("SymptomReport", 6, rmode="self", items=[1, 2], codes=["fever"], danger=False)
    out = rules_r4.evaluate([by_idx, by_code, by_flag, benign], PATIENT, d(10), TH)
    assert [c.tier for c in out] == ["red"] * 3
    assert "blood when coughing" in out[0].title and "chest pain" in out[1].title


# --------------------------------------------------------------------- R5


def test_r5_amber_at_three_red_at_seven_closed_by_reply() -> None:
    rows = [prompt(i) for i in range(10, 20)]
    assert rules_r5.evaluate(rows, PATIENT, d(12), TH) == []  # day 12 itself is still open
    amber = rules_r5.evaluate(rows, PATIENT, d(13), TH)
    assert len(amber) == 1 and amber[0].tier == "amber" and amber[0].opened_as_of == d(13)
    red = rules_r5.evaluate(rows, PATIENT, d(17), TH)
    assert red[0].tier == "red" and red[0].conflict_id == amber[0].conflict_id
    replied = rows + [taken(15)]
    out = rules_r5.evaluate(replied, PATIENT, d(16), TH)
    assert out[0].closed_as_of == d(15) and out[0].tier == "amber"


def test_r5_supporter_contact_breaks_streak() -> None:
    rows = [prompt(i) for i in range(10, 16)] + [visit(11)]
    assert rules_r5.evaluate(rows, PATIENT, d(13), TH) == []
    unreachable = [prompt(i) for i in range(10, 16)] + [visit(11, mode="unreachable")]
    assert len(rules_r5.evaluate(unreachable, PATIENT, d(13), TH)) == 1


def test_r5_reply_via_prompt_outbox_id() -> None:
    p = [prompt(i) for i in range(10, 14)]
    reply = ev(
        "DoseCheckin",
        12,
        rmode="self",
        status="unclear",
        for_date=None,
        prompt_outbox_id=p[1]["payload"]["outbox_id"],
    )
    assert rules_r5.evaluate(p + [reply], PATIENT, d(14), TH) == []


# --------------------------------------------------------------------- input shapes


def test_dataframe_and_model_inputs_match_dicts() -> None:
    from cm.contracts.domain import EventAdapter

    rows = _ravi_refill()
    base = rules_r1.evaluate(rows, PATIENT, d(60), TH)
    assert rules_r1.evaluate(pd.DataFrame(rows), PATIENT, d(60), TH) == base
    models = [
        EventAdapter.validate_python(
            {**{k: v for k, v in r.items() if k != "payload"}, **r["payload"]}
        )
        for r in rows
    ]
    assert rules_r1.evaluate(models, PATIENT, d(60), TH) == base
