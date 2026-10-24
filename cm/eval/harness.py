"""Lane J: 'Day 3 vs Day 60' evaluation harness.

The engine here is a self-contained baseline (decayed per-weekday beliefs over *reported*
adherence). ``cm.memory`` / ``cm.rules`` are still skeletons; when their public risk API lands, pass
it as ``predictor``. Labels use true behaviour (cm.contracts.evalsim: miss7 = >=2 true misses in
d+1..d+7). The sim clock is pinned per evaluated day via ``cm.core.clock``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cm.core import clock
from cm.sim.gen import DAY0, SimPatient, generate_patients, instant_for

from .metrics import auroc, brier, calibration_bins, ece

Predictor = Callable[[SimPatient, int], float]
EVAL_DAYS = (3, 60)
DECAY = 0.96


def label_miss7(p: SimPatient, d: int) -> int:
    return int(sum(1 for t in p.taken[d + 1 : d + 8] if not t) >= 2)


def baseline_predictor(p: SimPatient, d: int) -> float:
    """P(miss7) from reports up to and including day d only (no peeking)."""
    a, b = 3.0, 1.0  # weak prior: patients mostly take doses
    wd: dict[int, list[float]] = {}
    for day in range(d + 1):
        r = p.reported[day]
        if r is None:
            continue
        w = DECAY ** (d - day)
        a, b = a + w * r, b + w * (not r)
        cell = wd.setdefault((DAY0.weekday() + day) % 7, [0.0, 0.0])
        cell[0] += w * r
        cell[1] += w * (not r)
    miss = b / (a + b)
    p0 = p1 = 0.0
    p0 = 1.0
    for j in range(1, 8):  # P(>=2 misses in next 7 days), independence, weekday-aware
        x, y = wd.get((DAY0.weekday() + d + j) % 7, [0.0, 0.0])
        q = (y + miss * 2) / (x + y + 2)
        p1 = p1 * (1 - q) + p0 * q
        p0 *= 1 - q
    return min(0.999, max(0.001, 1 - p0 - p1))


def _last_week(p: SimPatient, d: int) -> float:
    rs = [r for r in p.reported[max(0, d - 6) : d + 1] if r is not None]
    if not rs:
        return 0.5
    return min(0.99, max(0.01, sum(1 for r in rs if not r) / len(rs) + 0.05))


def evaluate_day(pats: list[SimPatient], d: int, predictor: Predictor, train_rate: float) -> dict[str, Any]:
    clock.pin(instant_for(d))
    try:
        y = [label_miss7(p, d) for p in pats]
        out: dict[str, Any] = {"day": d, "n": len(y), "n_pos": sum(y), "as_of": clock.now().isoformat()}
        for name, ps in (
            ("model", [predictor(p, d) for p in pats]),
            ("pop_avg", [train_rate] * len(pats)),
            ("last_week", [_last_week(p, d) for p in pats]),
        ):
            bins = calibration_bins(ps, y)
            out[name] = {"brier": brier(ps, y), "auroc": auroc(ps, y), "ece": ece(bins)}
            if name == "model":
                out["calibration"] = bins
        return out
    finally:
        clock.unpin()


def run_eval(
    seed: int,
    patients: int = 40,
    days: int = 60,
    predictor: Predictor | None = None,
    out_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run Day 3 vs Day 60. Deterministic for a given seed. Writes JSON (+ PNG) if out_dir is given."""
    predictor = predictor or baseline_predictor
    pats = generate_patients(seed, patients, days)
    train = generate_patients(seed + 100_000, patients, days)  # independent cohort for the prior
    train_rate = sum(label_miss7(p, 30) for p in train) / len(train)
    report: dict[str, Any] = {
        "seed": seed,
        "n_patients": patients,
        "days": days,
        "label": "miss7",
        "eval_days": {str(d): evaluate_day(pats, d, predictor, train_rate) for d in EVAL_DAYS},
    }
    d3, d60 = report["eval_days"]["3"], report["eval_days"]["60"]
    report["improvement"] = {
        "brier_delta": d3["model"]["brier"] - d60["model"]["brier"],
        "ece_delta": d3["model"]["ece"] - d60["model"]["ece"],
    }
    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        plot = plot_calibration(report, out / f"eval_seed{seed}.png")
        report["plot"] = plot
        (out / f"eval_seed{seed}.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def plot_calibration(report: dict[str, Any], path: Path) -> str | None:
    """Small reliability diagram, Day 3 vs Day 60. Returns None if matplotlib is unavailable."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    fig, ax = plt.subplots(figsize=(4, 4), dpi=100)
    ax.plot([0, 1], [0, 1], "k--", lw=1, label="perfect")
    for d, c in (("3", "tab:red"), ("60", "tab:green")):
        bs = [b for b in report["eval_days"][d]["calibration"] if b["n"]]
        ax.plot([b["mean_pred"] for b in bs], [b["observed"] for b in bs], "o-", c=c, label=f"Day {d}")
    ax.set_xlabel("predicted P(miss7)")
    ax.set_ylabel("observed")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return str(path)
