"""Beta reporter trust with an interval (feature_specs/02 F5 B). Pure, seeded."""

from __future__ import annotations

from dataclasses import dataclass

from cm.memory.stats import as_of_key, beta_interval

PRIORS = {"self": (8.0, 2.0), "told": (6.0, 2.0), "witnessed": (19.0, 1.0)}


@dataclass(frozen=True)
class TrustBelief:
    mode: str
    score: float
    ci_low: float
    ci_high: float
    n: int
    state: str | None  # None, "hypothesis" (n>=5) or "confirmed" (n>=10 and CI width <= 0.35)


def reporter_trust(pid: str, mode: str, as_of, agreements: int, disagreements: int) -> TrustBelief:
    if mode not in PRIORS:
        raise ValueError(f"unknown reporter mode {mode!r}")
    if agreements < 0 or disagreements < 0:
        raise ValueError("counts must be >= 0")
    a0, b0 = PRIORS[mode]
    mean, lo, hi = beta_interval(
        a0 + agreements, b0 + disagreements, ("trust", pid, mode, as_of_key(as_of))
    )
    n = agreements + disagreements
    state = "confirmed" if n >= 10 and hi - lo <= 0.35 else "hypothesis" if n >= 5 else None
    return TrustBelief(mode, mean, lo, hi, n, state)
