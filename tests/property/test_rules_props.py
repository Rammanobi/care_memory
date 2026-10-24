"""Property tests for the R1-R6 reconciler: determinism, shuffle invariance, as_of bounds/monotonicity,
no future leakage, patient isolation. Random event histories are built with the rules test builders."""

from __future__ import annotations

import random
from typing import Any
from uuid import UUID

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cm.rules import reconcile_frame
from tests.unit.rules.builders import OTHER_PID, PATIENT, PID, TH, d, ev

PROPS = settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
CONTACTS = [UUID(int=0xC0 + i) for i in range(3)]
MAX_DAY = 60


@st.composite
def histories(draw: Any, pid: UUID = PID, allow_supersede: bool = False) -> list[dict[str, Any]]:
    n = draw(st.integers(0, 45))
    base = 1 if pid == PID else 10_000
    rows: list[dict[str, Any]] = [
        ev("RegimenChange", 0, pid=pid, event_id=UUID(int=base), regimen_to="first_line",
           line="first", effective_date=d(0).isoformat())  # fmt: skip
    ]
    for i in range(n):
        eid = UUID(int=base + i + 1)
        day = draw(st.integers(0, MAX_DAY))
        rec = day + draw(st.sampled_from([0, 0, 0, 1, 2, 5, 12]))
        kind = draw(st.sampled_from(
            ["dose", "dose", "dose", "dispense", "prompt", "visit", "symptom", "lab", "paid",
             "report", "contact", "note"]))  # fmt: skip
        kw: dict[str, Any] = {"pid": pid, "event_id": eid}
        if kind == "dose":
            r = ev("DoseCheckin", day, rec, rmode=draw(st.sampled_from(["self", "told"])),
                   source="telegram", status=draw(st.sampled_from(["taken", "missed"])),
                   for_date=d(day).isoformat(), **kw)  # fmt: skip
        elif kind == "dispense":
            r = ev("Dispense", day, rec, source="chemist", tablets=draw(st.sampled_from([30, 120])),
                   days_supply=draw(st.sampled_from([None, 7, 14, 30])), **kw)  # fmt: skip
        elif kind == "prompt":
            r = ev("CheckinPrompt", day, rec, outbox_id=str(UUID(int=base + 5000 + i)),
                   channel="telegram", for_date=d(day).isoformat(),
                   sent_at=f"{d(day).isoformat()}T09:00:00+05:30", **kw)  # fmt: skip
        elif kind == "visit":
            r = ev("SupporterVisit", day, rec, rmode="witnessed", mode="witnessed",
                   source="supporter", visit_date=d(day).isoformat(), **kw)  # fmt: skip
        elif kind == "symptom":
            r = ev("SymptomReport", day, rec, rmode="self", items=draw(st.sampled_from([[], [6], [1, 2]])),
                   codes=[], danger=draw(st.booleans()), **kw)  # fmt: skip
        elif kind == "lab":
            r = ev("LabResult", day, rec, source="lab", test="cbnaat", result="mtb_detected",
                   rif_resistant=draw(st.booleans()), report_date=d(day).isoformat(), **kw)  # fmt: skip
        elif kind == "paid":
            r = ev("PortalPayment", day, rec, source="portal", nikshay_id="NK1", month="2026-01",
                   amount=1000, status="paid", paid_on=d(day).isoformat(), **kw)  # fmt: skip
        elif kind == "report":
            r = ev("PaymentReport", day, rec, rmode="self", source="telegram", month="2026-01",
                   status=draw(st.sampled_from(["received", "not_received"])), **kw)  # fmt: skip
        elif kind == "contact":
            r = ev("HouseholdContactEvent", day, rec, rmode="told", source="supporter",
                   contact_id=str(draw(st.sampled_from(CONTACTS))),
                   action=draw(st.sampled_from(["listed", "listed", "screened"])), **kw)  # fmt: skip
        else:
            r = ev("ContextNote", day, rec, rmode="told", origin="supporter_text",
                   kind="household_declined", **kw)  # fmt: skip
        if allow_supersede and rows and draw(st.integers(0, 9)) == 0:
            r["supersedes"] = rows[-1]["event_id"]
        rows.append(r)
    return rows


as_of_days = st.integers(0, MAX_DAY + 10)


def _visible_ids(rows: list[dict[str, Any]], as_of_day: int) -> set[str]:
    return {
        f"E:{r['event_id']}"
        for r in rows
        if r["occurred_at"].date() <= d(as_of_day) and r["recorded_at"].date() <= d(as_of_day)
    }


@PROPS
@given(histories(allow_supersede=True), as_of_days, st.integers(0, 2**31))
def test_deterministic_and_shuffle_invariant(rows: list, day: int, seed: int) -> None:
    base = reconcile_frame(rows, PATIENT, d(day), TH)
    assert reconcile_frame(rows, PATIENT, d(day), TH) == base
    shuffled = rows[:]
    random.Random(seed).shuffle(shuffled)  # noqa: S311
    assert reconcile_frame(shuffled, PATIENT, d(day), TH) == base
    assert reconcile_frame(pd.DataFrame(shuffled), PATIENT, d(day), TH) == base
    assert len({c.conflict_id for c in base}) == len(base)


@PROPS
@given(histories(allow_supersede=True), as_of_days)
def test_as_of_bounds_and_evidence_is_visible(rows: list, day: int) -> None:
    as_of = d(day)
    vis = _visible_ids(rows, day)
    for c in reconcile_frame(rows, PATIENT, as_of, TH):
        assert c.patient_id == PID
        assert c.opened_as_of <= as_of
        assert c.closed_as_of is None or c.opened_as_of <= c.closed_as_of <= as_of
        assert set(c.evidence_ids) <= vis, "evidence cites an event not knowable at as_of"
        assert c.rule in {"R1", "R2", "R3", "R4", "R5", "R6"}


@PROPS
@given(histories(), as_of_days, st.lists(st.integers(1, 30), min_size=1, max_size=10))
def test_future_records_never_leak(rows: list, day: int, shifts: list[int]) -> None:
    base = reconcile_frame(rows, PATIENT, d(day), TH)
    future = []
    for i, s in enumerate(shifts):
        src = dict(rows[i % len(rows)])
        src["event_id"] = UUID(int=900_000 + i)
        src["recorded_at"] = src["recorded_at"].replace(
            year=d(day + s).year, month=d(day + s).month, day=d(day + s).day
        )
        src["occurred_at"] = min(src["occurred_at"], src["recorded_at"])
        future.append(src)
    assert reconcile_frame(rows + future, PATIENT, d(day), TH) == base


@PROPS
@given(histories(), histories(pid=OTHER_PID), as_of_days)
def test_other_patients_events_are_ignored(rows: list, other: list, day: int) -> None:
    assert reconcile_frame(rows + other, PATIENT, d(day), TH) == reconcile_frame(
        rows, PATIENT, d(day), TH
    )


@PROPS
@given(histories(), st.integers(0, MAX_DAY), st.integers(1, 15))
def test_as_of_monotonic_history_is_stable(rows: list, t1: int, gap: int) -> None:
    """Without corrections, moving as_of forward never forgets a conflict or rewrites when it opened."""
    early = {c.conflict_id: c for c in reconcile_frame(rows, PATIENT, d(t1), TH)}
    late = {c.conflict_id: c for c in reconcile_frame(rows, PATIENT, d(t1 + gap), TH)}
    for cid, c in early.items():
        assert cid in late, f"{c.rule} opened at {c.opened_as_of} vanished later"
        assert late[cid].opened_as_of == c.opened_as_of
        if c.closed_as_of is not None and late[cid].closed_as_of is None:
            # a closed conflict may reopen (one R6 episode per patient; an R5 run regains its first prompt)
            # only when something new was recorded after t1: time passing alone never reopens it
            news = [r for r in rows if d(t1) < r["recorded_at"].date() <= d(t1 + gap)]
            assert news, f"{c.rule} reopened without any new record"
