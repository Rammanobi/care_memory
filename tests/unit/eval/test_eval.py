import json

from cm.core import clock
from cm.eval.harness import run_eval
from cm.eval.metrics import auroc, brier, calibration_bins, ece
from cm.jobs.eval_job import run_eval_job


def test_metrics():
    assert brier([1.0, 0.0], [1, 0]) == 0.0
    assert auroc([0.9, 0.1], [1, 0]) == 1.0
    assert auroc([0.5, 0.5], [1, 1]) is None
    assert ece(calibration_bins([0.5] * 10, [1] * 5 + [0] * 5)) == 0.0


def test_seeded_run_reproducible_and_clock_unpinned():
    assert run_eval(2042) == run_eval(2042)
    assert clock.now().year >= 2026 and not clock._pins


def test_day60_beats_day3():
    r = run_eval(2042, patients=60)
    assert r["improvement"]["brier_delta"] > 0
    assert r["eval_days"]["60"]["model"]["brier"] < r["eval_days"]["60"]["pop_avg"]["brier"]


def test_job_writes_json_and_plot(tmp_path):
    r = run_eval_job(2077, out_dir=tmp_path)
    data = json.loads((tmp_path / "eval_seed2077.json").read_text())
    assert data["eval_days"]["60"]["calibration"]
    if r.get("plot"):
        assert (tmp_path / "eval_seed2077.png").exists()


def test_reject_train_seed(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        run_eval_job(1005, out_dir=tmp_path)
