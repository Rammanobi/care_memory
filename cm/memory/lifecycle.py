"""Belief lifecycle (feature_specs/02 F5 E), pure: hypothesis -> confirmed -> dormant -> retired."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class BeliefState:
    state: str  # hypothesis | confirmed | dormant | retired
    first_day: int
    last_support_day: int
    low_since_day: int | None = None  # first day posterior fell below 0.30, None if not low
    retired_reason: str | None = None


def advance_belief_state(
    belief: BeliefState,
    as_of_day: int,
    posterior: float,
    *,
    confirm_met: bool,
    supported_today: bool = False,
    doctor_reject: bool = False,
) -> BeliefState:
    """One daily step. Retired is terminal; a doctor reject retires from any state."""
    if belief.state == "retired":
        return belief
    if doctor_reject:
        return replace(belief, state="retired", retired_reason="doctor_reject")
    b = replace(belief, last_support_day=as_of_day) if supported_today else belief
    low = (
        (b.low_since_day if b.low_since_day is not None else as_of_day)
        if posterior < 0.30
        else None
    )
    b = replace(b, low_since_day=low)
    since_support = as_of_day - b.last_support_day
    if b.state == "hypothesis":
        if confirm_met:
            return replace(b, state="confirmed")
        if (low is not None and as_of_day - low >= 14) or as_of_day - b.first_day >= 42:
            return replace(b, state="retired", retired_reason="not_supported")
    elif b.state == "confirmed" and since_support >= 21:
        return replace(b, state="dormant")
    elif b.state == "dormant":
        if supported_today and confirm_met:
            return replace(b, state="confirmed")
        if since_support >= 42:
            return replace(b, state="retired", retired_reason="no_support_42d")
    return b
