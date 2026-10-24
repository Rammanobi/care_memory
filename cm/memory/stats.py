"""Deterministic statistics helpers for the memory engine (stdlib only, seeded, no clock, no LLM)."""

from __future__ import annotations

import random
import zlib


def seed_for(*parts: object) -> int:
    """Stable 32-bit seed from parts (never ``hash()``, which is salted per process)."""
    return zlib.crc32("|".join(str(p) for p in parts).encode())


def rng(*parts: object) -> random.Random:
    return random.Random(seed_for(*parts))  # noqa: S311 (seeded stats, not crypto)


def percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolated percentile of an already sorted list, q in [0, 1]."""
    if not sorted_vals:
        raise ValueError("empty sample")
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def beta_interval(
    alpha: float, beta: float, key: tuple, draws: int = 2000
) -> tuple[float, float, float]:
    """(mean, p05, p95) of Beta(alpha, beta); the interval is Monte Carlo with a seeded RNG."""
    r = rng("beta", *key)
    xs = sorted(r.betavariate(alpha, beta) for _ in range(draws))
    return alpha / (alpha + beta), percentile(xs, 0.05), percentile(xs, 0.95)


def as_of_key(as_of: object) -> str:
    return as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of)
