"""reconcile_frame / reconcile / merge_upsert / fast_path / drafts."""

from __future__ import annotations

import random
from datetime import timedelta
from uuid import uuid4

import pandas as pd

from cm.rules import (
    draft_for_conflict,
    drafts_for_opened,
    fast_path,
    merge_upsert,
    open_conflicts,
    reconcile,
    reconcile_frame,
)
from cm.rules.reconcile import patient_from_events

from .builders import OTHER_PID, PATIENT, PID, TH, d, dispense, ev, prompt, regimen, rules_of, taken
from .builders import contact as hh


def _ravi() -> list[dict]:
    rows = [regimen(0), dispense(0), dispense(44)] + [
        taken(i) for i in range(0, 60) if i not in (40, 41, 42)
    ]
    rows += [prompt(i) for i in range(40, 43)]
    rows.append(ev("SymptomReport", 50, rmode="self", items=[7], codes=[], danger=True))
    rows.append(hh(3, uuid4(), "listed", relation="spouse"))
    return rows


def test_reconcile_frame_runs_all_rules() -> None:
    out = reconcile_frame(pd.DataFrame(_ravi()), PATIENT, d(60), TH)
    assert {c.rule for c in out} == {"R1", "R4", "R5", "R6"}
    assert rules_of(out, "R1")[0].closed_as_of == d(44)
    assert rules_of(out, "R4")[0].tier == "red"
    assert len({c.conflict_id for c in out}) == len(out)


def test_reconcile_is_deterministic_under_shuffle() -> None:
    rows = _ravi()
    base = reconcile_frame(rows, PATIENT, d(60), TH)
    for seed in range(20):
        shuffled = rows[:]
        random.Random(seed).shuffle(shuffled)  # noqa: S311
        assert reconcile_frame(shuffled, PATIENT, d(60), TH) == base


def test_reconcile_as_of_ignores_future_and_other_patients() -> None:
    rows = _ravi() + [
        ev("SymptomReport", 5, rec=70, items=[6], danger=True)
    ]  # recorded after as_of
    rows.append(ev("SymptomReport", 5, pid=OTHER_PID, items=[6], danger=True))
    out = reconcile_frame(rows, PATIENT, d(60), TH)
    assert len(rules_of(out, "R4")) == 1


def test_superseded_and_tombstoned_events_are_ignored() -> None:
    bad = ev("SymptomReport", 10, items=[6], danger=True)
    fix = ev("SymptomReport", 10, rec=11, items=[], danger=False, supersedes=bad["event_id"])
    gone = ev("SymptomReport", 12, items=[6], danger=True)
    gone["type"] = "Tombstone"
    assert rules_of(reconcile_frame([regimen(0), bad, fix, gone], PATIENT, d(13), TH), "R4") == []


def test_reconcile_with_injected_loader() -> None:
    rows = _ravi()
    out = reconcile(PID, d(60), thresholds=TH, load_events=lambda pid, as_of: rows)
    assert out == reconcile_frame(rows, PATIENT, d(60), TH)
    assert patient_from_events(PID, rows)["treatment_start"] == d(0)


def test_merge_upsert_keeps_first_opened_and_closes_vanished() -> None:
    out = reconcile_frame(_ravi(), PATIENT, d(60), TH)
    r4 = rules_of(out, "R4")[0]
    earlier = r4.model_copy(update={"opened_as_of": r4.opened_as_of - timedelta(days=2)})
    ghost = r4.model_copy(update={"conflict_id": uuid4(), "closed_as_of": None})
    merged = merge_upsert([earlier, ghost], out, d(60))
    by_id = {c.conflict_id: c for c in merged}
    assert by_id[r4.conflict_id].opened_as_of == earlier.opened_as_of
    assert by_id[ghost.conflict_id].closed_as_of == d(60)


def test_fast_path_runs_r2_and_r4_only() -> None:
    danger = ev("SymptomReport", 9, items=[5], danger=True)
    assert [c.rule for c in fast_path(danger)] == ["R4"]
    lab = ev(
        "LabResult",
        9,
        test="cbnaat",
        result="mtb_detected",
        rif_resistant=True,
        report_date=d(9).isoformat(),
    )
    assert [c.rule for c in fast_path(lab, context=[regimen(0)], patient=PATIENT)] == ["R2"]
    assert fast_path(lab, context=[regimen(0, line="second")], patient=PATIENT) == []
    assert fast_path(taken(9)) == [] and fast_path(dispense(9)) == []
    # fast path and nightly agree on the conflict id (one implementation)
    nightly = reconcile_frame([regimen(0), danger], PATIENT, d(10), TH)
    assert (
        fast_path(danger, patient=PATIENT)[0].conflict_id == rules_of(nightly, "R4")[0].conflict_id
    )


def test_drafts_are_doctor_only_cited_and_deduped() -> None:
    out = reconcile_frame(_ravi(), PATIENT, d(60), TH)
    opened = open_conflicts(out, d(60))
    drafts = drafts_for_opened([], out, d(60))
    assert len(drafts) == len(opened) and drafts[0].tier == "red"
    for dr in drafts:
        p = dr.proposal
        assert (
            dr.kind == "conflict"
            and p.audience == "doctor"
            and p.channel is None
            and p.recipients == []
        )
        assert p.sentences[0].refs[0] == f"C:{dr.conflict_id}" and len(p.sentences[0].refs) >= 2
        assert dr.dedupe_key == f"conflict:{dr.conflict_id}"
    assert drafts_for_opened(out, out, d(60)) == []  # already known: no duplicate approvals
    closed_r1 = rules_of(out, "R1")[0]
    assert all(dr.conflict_id != str(closed_r1.conflict_id) for dr in drafts)
    assert draft_for_conflict(closed_r1, patient_token="P-0042").proposal.title.endswith("P-0042")
