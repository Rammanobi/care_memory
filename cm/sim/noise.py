"""Lane B: reporting noise applied between true behaviour and what the system observes."""

from __future__ import annotations

import random


def observe(rng: random.Random, taken: bool, over_reporter: bool, report_rate: float = 0.92) -> bool | None:
    """What the patient reports for one day: True/False, or None when nothing is reported.

    Over-reporters claim a dose on most missed days; everyone forgets to tap sometimes.
    """
    if rng.random() > report_rate:
        return None
    if taken:
        return True
    return True if (over_reporter and rng.random() < 0.7) else False
