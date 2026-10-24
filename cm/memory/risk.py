"""Risk score with an uncertainty interval (feature_specs/02 F5 D). Pure, seeded, no LLM.

v1 uses fixed, documented logistic coefficients (``MODEL_VERSION``); a trained model replaces them in
``train_risk``. The interval is the 5th/95th percentile of 500 seeded draws over the adherence Beta posterior.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from cm.memory.stats import as_of_key, percentile, rng

MODEL_VERSION = "risk_v1_fixed"
DRAWS = 500
INTERCEPT = -2.2
COEF = {
    "adherence_miss": 5.0,
    "refill_gap": 0.08,
    "consecutive_unanswered": 0.35,
    "weekday_flag": 0.5,
}


@dataclass(frozen=True)
class RiskResult:
    p: float
    ci_low: float
    ci_high: float
    drivers: tuple[tuple[str, float], ...]  # top positive contributions
    model_version: str


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _logit(adh_miss: float, refill_gap: float, unanswered: float, weekday: float) -> float:
    return (
        INTERCEPT
        + COEF["adherence_miss"] * adh_miss
        + COEF["refill_gap"] * refill_gap
        + COEF["consecutive_unanswered"] * unanswered
        + COEF["weekday_flag"] * weekday
    )


def score_risk(
    pid: str,
    as_of,
    *,
    adh_alpha: float,
    adh_beta: float,
    refill_gap_days: int = 0,
    consecutive_unanswered: int = 0,
    weekday_flag: bool = False,
) -> RiskResult:
    """p from the posterior mean; (ci_low, ci_high) over adherence draws. Fewer observations, wider interval."""
    if adh_alpha <= 0 or adh_beta <= 0:
        raise ValueError("Beta parameters must be > 0")
    gap, un, wd = (
        float(max(0, refill_gap_days)),
        float(max(0, consecutive_unanswered)),
        float(bool(weekday_flag)),
    )
    miss_mean = adh_beta / (adh_alpha + adh_beta)
    p = _sigmoid(_logit(miss_mean, gap, un, wd))
    r = rng("risk", pid, as_of_key(as_of))
    ps = sorted(
        _sigmoid(_logit(1 - r.betavariate(adh_alpha, adh_beta), gap, un, wd)) for _ in range(DRAWS)
    )
    contrib = {
        "adherence_miss": COEF["adherence_miss"] * (miss_mean - 0.1),
        "refill_gap": COEF["refill_gap"] * gap,
        "consecutive_unanswered": COEF["consecutive_unanswered"] * un,
        "weekday_flag": COEF["weekday_flag"] * wd,
    }
    top = sorted(((k, v) for k, v in contrib.items() if v > 0), key=lambda kv: (-kv[1], kv[0]))[:3]
    return RiskResult(p, percentile(ps, 0.05), percentile(ps, 0.95), tuple(top), MODEL_VERSION)
