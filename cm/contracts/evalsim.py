"""Sim, task-run, eval and channel contracts (tier 2).

FROZEN at ``contracts-v1``.

Label definitions (M5, frozen; also in ``docs/maths.md`` and ``frozen_spec_hash``):

* **miss7** = 1 if there are **>= 2 true misses** (forced misses included) in days
  ``d+1 .. d+7``.
* **dropout14** = 1 if a run of **>= 7 consecutive true misses** lies inside
  ``d+1 .. d+14``. This is the displayed ``RiskScore.p``.

Seeds: train 1000-1099, calibrate 1100-1149, evaluate >= 2000. Demo seed 42 is
allowed but flagged ``demo_cohort``. ``GET /eval?seed`` with a seed < 2000 other
than 42 returns 422. Precomputed: 2042, 2077, 2026.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from .agents import ErrorClass, TaskState
from .domain import CMModel, RuleId

# ---------------------------------------------------------------------------
# Sim
# ---------------------------------------------------------------------------


class SimClock(CMModel):
    """The active ``sim_clock`` row."""

    run_id: UUID
    seed: int
    sim_day: int = Field(ge=0)
    day0_date: date
    max_computed_day: int
    escalation_offset_hours: float = Field(0, description="Honoured only when DEMO_MODE=1")
    offline: bool = Field(False, description="CM_OFFLINE=1")
    status: Literal["seeding", "ready"]


class SimRunOut(CMModel):
    """``POST /sim/reset`` (no params = restore demo seed 42)."""

    run_id: UUID
    seed: int
    patients: int
    days: int
    task_id: str | None = Field(default=None, description="cm-seed execution tracked in task_runs")
    restored_demo: bool = False


class SimAdvanceOut(CMModel):
    """``POST /sim/advance``. ``mode=full`` on GCP returns 202 with ``task_id`` (cm-nightly execution)."""

    clock: SimClock
    mode: Literal["fast", "full"]
    task_id: str | None = None


class EscalationOffsetIn(CMModel):
    hours: float = Field(ge=0, le=96)


class SimInboxItem(CMModel):
    id: int
    persona: str = Field(description="e.g. ravi, lakshmi, dr_rao")
    channel: str
    direction: Literal["in", "out"]
    body: str
    buttons: list[dict[str, str]] = Field(default_factory=list, description="[{text, callback_data}]")
    created_at: datetime


class SimReplyIn(CMModel):
    callback_data: str | None = None
    text: str | None = Field(default=None, max_length=1000)


class SimInjectIn(CMModel):
    """P1 scenario injector."""

    patient_token: str
    scenario: Literal["danger_symptom", "rif_resistant_lab", "payment_failed", "go_silent", "late_csv"]
    day: int | None = None


# ---------------------------------------------------------------------------
# Task runs
# ---------------------------------------------------------------------------


class TaskRunStatus(CMModel):
    """``GET /task-runs/{task_id}``. Field is ``state`` (T10)."""

    task_id: str
    task_type: str
    state: TaskState
    attempt: int
    progress: float | None = Field(default=None, ge=0, le=1)
    step: str | None = Field(default=None, description="'generating', 'nightly', 'scoring'")
    error: str | None = None
    error_class: ErrorClass | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Eval (M6: 04's nested shape + facts.totals + safety + excluded/degraded)
# ---------------------------------------------------------------------------

PatternKind = Literal["market_day", "payday", "over_reporter", "drift", "payment_failure"]


class Metric(CMModel):
    brier: float
    auroc: float | None = Field(default=None, description="None on a single-class day")


class MetricCI(Metric):
    brier_ci: tuple[float, float]
    auroc_ci: tuple[float, float] | None = None


class CurvePoint(CMModel):
    """One evaluated day. UI reads ``curves.miss7[i].model.auroc``."""

    day: int
    model: MetricCI
    pop_avg: Metric
    last_week: Metric
    n_pos: int


class EvalCurves(CMModel):
    miss7: list[CurvePoint] = Field(default_factory=list)
    dropout14: list[CurvePoint] = Field(default_factory=list)


class FunnelPoint(CMModel):
    day: int
    mean_ci_width: float
    coverage90: float = Field(ge=0, le=1)


class PatternScore(CMModel):
    planted: int
    caught: int
    false: int
    false_retired: int
    missed: int
    precision: float | None = None
    recall: float | None = None
    median_days_to_detect: float | None = None


class MissedPattern(CMModel):
    patient_token: str
    pattern: PatternKind
    reason: Literal["insufficient_observations", "below_threshold", "wrong_subject"]
    detail: str | None = None


class FactsScorecard(CMModel):
    by_pattern: dict[PatternKind, PatternScore]
    totals: PatternScore = Field(description="Sum over patterns (no client maths)")
    missed: list[MissedPattern] = Field(default_factory=list, description="Always rendered")
    no_pattern_fp_rate: float | None = None


class RuleScore(CMModel):
    precision: float | None = None
    recall: float | None = None
    planted: int | None = None
    fired: int | None = None


class Safeguards(CMModel):
    seed_in_train: bool
    demo_cohort: bool = False
    permutation_auroc: float | None = None
    leak_suspected: bool = False
    frozen_spec_hash: str
    spec_changed_after_view: bool = False
    scripted_excluded: list[str] = Field(default_factory=list)


class Timings(CMModel):
    gen_s: float
    engine_s: float
    rules_s: float
    metrics_s: float
    facts_s: float | None = None
    total_s: float


class SafetyCounters(CMModel):
    banned_term_violations: int = 0
    unapproved_sends: int = 0
    red_auto_sent: int = 0


class NarrationScore(CMModel):
    """cm-eval job only (LLM judge); None in the live path."""

    sampled: int
    citation_coverage: float | None = None
    number_accuracy: float | None = None
    mean_cut_ratio: float | None = None
    fallback_rate: float | None = None
    judge_mean_score: float | None = None
    skipped_reason: str | None = None


class EvalReport(CMModel):
    """``GET /eval?seed``. See module docstring for miss7 / dropout14 definitions."""

    seed: int
    gen_version: str
    engine_version: str
    model_version: str
    n_patients: int
    n_scored: int
    cached: bool = False
    computed_in_ms: int | None = None
    curves: EvalCurves
    funnel: list[FunnelPoint] = Field(default_factory=list)
    facts: FactsScorecard
    trust_mae: float | None = None
    rules: dict[RuleId, RuleScore] = Field(default_factory=dict)
    safeguards: Safeguards
    timings: Timings
    safety: SafetyCounters = Field(default_factory=SafetyCounters)
    narration: NarrationScore | None = None
    ablation: dict | None = None
    excluded: list[str] = Field(default_factory=list, description="Patient tokens excluded after engine errors")
    degraded: bool = Field(False, description="True when > 5% excluded")


class EvalRunStatus(CMModel):
    """``GET /eval/runs/{run_id}`` (202 Location target)."""

    run_id: UUID
    seed: int
    status: Literal["running", "done", "failed"]
    report: EvalReport | None = None
    task_id: str | None = None


# ---------------------------------------------------------------------------
# Channels (kill switches; cut #1)
# ---------------------------------------------------------------------------


class ChannelStatus(CMModel):
    channel: Literal["telegram", "gmail", "calendar", "wearable", "supporter_web"]
    enabled: bool
    mode: Literal["live", "simulated", "off"]
    healthy: bool
    last_seen_at: datetime | None = None
    fallback: str | None = None
    locked: bool = Field(False, description="supporter_web is always on")


class ChannelToggleIn(CMModel):
    enabled: bool
    reason: str = Field(min_length=3, max_length=200)


__all__ = [
    "SimClock", "SimRunOut", "SimAdvanceOut", "EscalationOffsetIn", "SimInboxItem", "SimReplyIn", "SimInjectIn",
    "TaskRunStatus", "PatternKind", "Metric", "MetricCI", "CurvePoint", "EvalCurves", "FunnelPoint",
    "PatternScore", "MissedPattern", "FactsScorecard", "RuleScore", "Safeguards", "Timings", "SafetyCounters",
    "NarrationScore", "EvalReport", "EvalRunStatus", "ChannelStatus", "ChannelToggleIn",
]
