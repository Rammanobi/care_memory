"""Pooled Bayesian weekday-miss detector (feature_specs/02 F5 A). Pure, seeded, no LLM."""

from __future__ import annotations

from dataclasses import dataclass

from cm.memory.stats import as_of_key, percentile, rng

ALPHA_P, BETA_P, KAPPA, DELTA, DRAWS = 1.0, 9.0, 4.0, 0.20, 4000


@dataclass(frozen=True)
class WeekdayBelief:
    weekday: str
    posterior: float  # P(rate on this weekday exceeds baseline by > 0.20)
    effect: float  # mean of delta
    ci_low: float
    ci_high: float
    n_instances: int  # misses on that weekday
    state: str | None  # None, "hypothesis" or "confirmed"


def weekday_effect(
    pid: str, weekday: str, as_of, misses: int, total: int, rest_misses: int, rest_total: int
) -> WeekdayBelief:
    """Belief that ``weekday`` is missed more than the patient's own baseline, with a 90% interval on delta."""
    if (
        min(misses, total, rest_misses, rest_total) < 0
        or misses > total
        or rest_misses > rest_total
    ):
        raise ValueError("inconsistent counts")
    r = rng("weekday", pid, weekday, as_of_key(as_of))
    mu = (ALPHA_P + rest_misses) / (ALPHA_P + BETA_P + rest_total)
    deltas = []
    for _ in range(DRAWS):
        base = r.betavariate(ALPHA_P + rest_misses, BETA_P + rest_total - rest_misses)
        mu_k = r.betavariate(KAPPA * mu + misses, KAPPA * (1 - mu) + total - misses)
        deltas.append(mu_k - base)
    p = sum(d > DELTA for d in deltas) / DRAWS
    deltas.sort()
    state = (
        "confirmed"
        if misses >= 4 and p >= 0.90
        else "hypothesis"
        if misses >= 2 and p >= 0.60
        else None
    )
    return WeekdayBelief(
        weekday,
        p,
        sum(deltas) / DRAWS,
        percentile(deltas, 0.05),
        percentile(deltas, 0.95),
        misses,
        state,
    )


def detect_weekday_misses(
    pid: str, as_of, weekday_miss: dict[str, tuple[int, int]]
) -> list[WeekdayBelief]:
    """Run ``weekday_effect`` for every weekday given ``{weekday: (misses, total)}``; returns those with a state."""
    out = []
    for wd, (m, n) in sorted(weekday_miss.items()):
        rm = sum(v[0] for k, v in weekday_miss.items() if k != wd)
        rn = sum(v[1] for k, v in weekday_miss.items() if k != wd)
        b = weekday_effect(pid, wd, as_of, m, n, rm, rn)
        if b.state:
            out.append(b)
    return out
