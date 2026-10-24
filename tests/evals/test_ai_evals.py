"""AI eval suite, offline mode (CI default): one pytest case per golden case in fixtures/ai_evals/.

Cases tagged ``known_gap`` are open bugs: xfail(strict=True), so fixing the bug turns the run red until the
fixture tag is removed. The live mode (real WORKER model + JUDGE) is `python -m cm.eval.ai_eval --live`;
the ``live`` test below only checks its wiring and never calls a provider.
"""

from __future__ import annotations

import json

import pytest

from cm.eval import ai_eval as ae

CASES = ae.offline_cases()


@pytest.mark.parametrize("case", CASES, ids=[f"{c.category}:{c.case_id}" for c in CASES])
def test_golden_case(case: ae.Case) -> None:
    r = ae.run_case(case)
    failed = {k: v for k, v in r.checks.items() if not v}
    if case.known_gap:
        if r.passed:
            pytest.fail(
                f"known gap {case.known_gap} now passes: remove the known_gap tag from the fixture"
            )
        pytest.xfail(f"{case.known_gap}: {ae.KNOWN_GAPS[case.known_gap]}")
    assert r.passed, (
        f"failed checks {failed}; detail {json.dumps(r.detail, default=str, ensure_ascii=False)[:600]}"
    )


def test_every_known_gap_is_documented() -> None:
    assert {c.known_gap for c in CASES if c.known_gap} <= set(ae.KNOWN_GAPS)


def test_coverage_floor() -> None:
    """The golden set keeps its breadth: every category, both languages, adversarial Ask-box kinds."""
    cats = {c.category for c in CASES}
    assert cats == set(ae.CATEGORIES)
    assert {c.lang for c in CASES} >= {"en", "te"}
    kinds = {s["kind"] for s in ae.load("ask_box")["safety"]}
    assert kinds >= {"advice", "injection", "pii", "unanswerable"}
    assert len(CASES) >= 90


def test_text_detectors() -> None:
    assert ae.advice_hits("Double the dose for PT-0142.")
    assert not ae.advice_hits("I cannot advise on changing the dose; only the treating doctor can.")
    assert ae.advice_hits("This suggests drug resistance.")
    assert not ae.tone_ok("The patient is careless!")
    assert ae.pii_hits("call 9876543210") == ["PHONE"]
    assert ae.abstained("Weight is not in the record [1].")
    assert ae.banned_hits("TB") and ae.banned_hits("క్షయ") and not ae.banned_hits("Missed 2 doses")


def test_report_is_written(tmp_path) -> None:
    rep = ae.run_suite(live=False)
    ae.write_reports(rep, tmp_path, None)
    data = json.loads((tmp_path / "ai_eval_offline.json").read_text(encoding="utf-8"))
    assert data["summary"]["unexpected_failures"] == []
    assert set(data["longitudinal"]) >= {"3", "30", "60"}
    assert "| cite_or_cut |" in (tmp_path / "ai_eval_offline.md").read_text(encoding="utf-8")


def test_live_mode_is_capped_and_flash_only(monkeypatch) -> None:
    """Wiring only, no network: the live governor stops at the cap, and live_env refuses a non-flash WORKER."""
    gov = ae.live_governor(1.0)
    assert gov.limits.event_usd == 1.0 and gov.limits.spendable_usd == 1.0
    gov.record(
        model="x", tokens_in=1, tokens_out=40_000, task_id="ai-eval-live-x"
    )  # 1.2 USD at default price
    assert not ae._budget_left(gov)
    monkeypatch.setenv("WORKER_MODEL", "openai:gpt-x")
    with pytest.raises(SystemExit):
        ae.live_env()
