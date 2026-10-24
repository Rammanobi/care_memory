"""Lane B: deterministic seeded patient simulator (60-day course plus a label horizon).

Pure stdlib ``random.Random(seed)``; no wall clock. Day indices are sim days, mapped to instants
through ``cm.core.clock.sim_instant`` so the engine/eval can pin the sim clock.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date

from cm.core.clock import sim_instant

from .noise import observe

DAY0 = date(2026, 1, 5)  # a Monday
LABEL_HORIZON = 14  # truth is generated beyond the visible course so day-60 labels exist
PATTERNS = ("market_day", "payday", "over_reporter", "drift")


@dataclass
class SimPatient:
    token: str
    base_rate: float
    patterns: list[str]
    taken: list[bool]  # true behaviour, len = days + LABEL_HORIZON
    reported: list[bool | None]  # what the system sees (None after the visible course)
    day0: date = DAY0
    meta: dict = field(default_factory=dict)


def _p_taken(day: int, base: float, patterns: list[str], market_dow: int) -> float:
    p = base
    dow = (DAY0.weekday() + day) % 7
    if "market_day" in patterns and dow == market_dow:
        p -= 0.55
    if "payday" in patterns and day % 30 in (0, 1, 2):
        p -= 0.45
    if "drift" in patterns:
        p -= 0.012 * day
    return min(0.99, max(0.02, p))


def generate_patients(seed: int, patients: int, days: int) -> list[SimPatient]:
    """Deterministic generator: same (seed, patients, days) gives identical output."""
    rng = random.Random(seed)
    out: list[SimPatient] = []
    for i in range(patients):
        prng = random.Random(rng.getrandbits(64))
        base = prng.betavariate(8, 2)
        pats = [x for x in PATTERNS if prng.random() < 0.2]
        market_dow = prng.randrange(7)
        n = days + LABEL_HORIZON
        taken = [prng.random() < _p_taken(d, base, pats, market_dow) for d in range(n)]
        over = "over_reporter" in pats
        reported = [observe(prng, t, over) if d < days else None for d, t in enumerate(taken)]
        out.append(SimPatient(f"P{seed}-{i:03d}", round(base, 4), pats, taken, reported, DAY0))
    return out


def instant_for(day: int):
    """The sim-clock instant for a day (18:00 IST, as UTC)."""
    return sim_instant(DAY0, day)
