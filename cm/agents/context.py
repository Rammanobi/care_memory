"""Run context shared by the tools and the narrator (one per orchestrator run)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from cm.core import budget as _budget
from cm.memory.features import PatientFeatures


@dataclass
class RunContext:
    patient_id: UUID
    token: str
    as_of: datetime
    task_id: str
    thread_id: str
    events: list[dict[str, Any]]
    features: PatientFeatures
    model: Any = None  # narrator model (GovernedModel or a fake with .invoke)
    breaker: _budget.RunBreaker | None = None
    cards: dict[str, dict[str, Any]] = field(default_factory=dict)  # card_id -> card
    approvals: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
