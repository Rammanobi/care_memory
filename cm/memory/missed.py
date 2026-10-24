"""Missed-dose features as of a time: thin pure wrapper over ``cm.memory.features`` (no clock, no LLM)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from cm.memory.features import PatientFeatures, compute_features


def missed_dose_features(events: list[dict[str, Any]], as_of: datetime) -> PatientFeatures:
    """Events come from ``cm.store.as_of`` / events_repo; future events are filtered again here."""
    return compute_features(events, as_of)
