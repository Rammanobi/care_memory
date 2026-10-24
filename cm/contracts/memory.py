"""Memory contracts: L1-L3 engine outputs, snapshots, narration and the nightly report.

FROZEN at ``contracts-v1``.

Rules that shape these models:
* Statistics and rules decide; LLMs narrate only (P1). Every number in a card
  must match a field of a cited object (cite-or-cut validator).
* Citation refs are strings ``"{letter}:{id}"`` with letter in E/B/C/R/G/D
  (``R:{patient_token}@{day}`` for risk). See :data:`cm.contracts.domain.RefLetter`.
* ``InMemoryResult`` (M1) is a frozen dataclass of two DataFrames and is NOT a
  Pydantic model; its column lists are pinned here as constants.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from .domain import (
    Audience,
    BeliefKind,
    BeliefState,
    CMModel,
    ConsentSource,
    EventSource,
    RefLetter,
    ReporterMode,
    RuleId,
    Tier,
    Weekday,
)

# ---------------------------------------------------------------------------
# M1 InMemoryResult column contracts (pandas, not Pydantic)
# ---------------------------------------------------------------------------

IN_MEMORY_RISK_COLUMNS: tuple[str, ...] = (
    "patient_token", "day", "p_miss7", "miss7_ci_low", "miss7_ci_high", "p_dropout14", "ci_low", "ci_high",
)
"""Columns of ``InMemoryResult.risk`` returned by ``cm.memory.pipeline.run_in_memory`` (M1)."""

IN_MEMORY_BELIEF_COLUMNS: tuple[str, ...] = (
    "patient_token", "day", "belief_id", "kind", "subject", "state", "posterior", "ci_low", "ci_high",
    "confirmed_at", "retired_at",
)
"""Columns of ``InMemoryResult.beliefs`` (M1)."""


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


class CitationRef(CMModel):
    """UI-ready form of a ``card_citations`` row or an evidence id."""

    ref_type: RefLetter
    ref_id: str = Field(description="UUID for E/B/C/G/D; 'P-0042@60' for R")
    label: str = Field(description="Human label, e.g. 'Chemist CSV d44'")
    sim_day: int | None = None

    @property
    def ref(self) -> str:
        """Canonical ``{letter}:{id}`` string used in ``Sentence.refs``."""
        return f"{self.ref_type}:{self.ref_id}"


# ---------------------------------------------------------------------------
# Engine (L1-L3)
# ---------------------------------------------------------------------------


class FeatureVector(CMModel):
    """Daily features for one patient (row of ``features_daily.features``). Built by lane C from L0 only."""

    patient_id: UUID
    as_of: date
    day: int = Field(ge=0, description="Treatment day of as_of")
    engine_version: str
    adh_7: float | None = Field(default=None, ge=0, le=1, description="Mean trust-weighted q_d over 7 days")
    adh_14: float | None = Field(default=None, ge=0, le=1)
    adh_28: float | None = Field(default=None, ge=0, le=1)
    adh_decay: float | None = Field(default=None, ge=0, le=1, description="Exponential 14-day half-life mean")
    n_eff: float | None = Field(default=None, ge=0, description="Effective sample size of the decayed mean")
    adh_alpha: float | None = Field(default=None, gt=0, description="Beta posterior alpha (risk Monte Carlo)")
    adh_beta: float | None = Field(default=None, gt=0, description="Beta posterior beta")
    adh_7_self: float | None = Field(default=None, ge=0, le=1, description="Self-reported-only adherence, 7 d")
    weekday_miss: dict[Weekday, tuple[int, int]] = Field(default_factory=dict, description="(misses, total) per weekday over 56 d")
    payday_miss: tuple[int, int] | None = None
    on_hand_pills: float | None = None
    refill_gap_days_28: int | None = None
    days_since_witnessed: int | None = None
    reply_min_median_7: float | None = None
    reply_ln_decay: float | None = None
    answer_rate_7: float | None = Field(default=None, ge=0, le=1)
    consecutive_unanswered: int = 0
    weight_last: float | None = None
    weight_slope_kg_30d: float | None = None
    payment_flag: bool = False
    symptom_flag_14: bool = False
    wearable_rhr_z: float | None = None
    channel_coverage_14: float | None = Field(default=None, ge=0, le=1)


class Detection(CMModel):
    """Internal detector output (E8, not an event). Input to the belief lifecycle step."""

    kind: BeliefKind
    subject: str | None = None
    as_of: date
    posterior: float = Field(ge=0, le=1)
    effect: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    n_instances: int = 0
    event_ids: list[UUID] = Field(default_factory=list)
    change_day: int | None = Field(default=None, description="CUSUM change point (reply_drift)")


class Belief(CMModel):
    """A belief snapshot (row of ``beliefs`` keyed by belief_id + as_of)."""

    belief_id: UUID
    patient_id: UUID | None = None
    as_of: date | None = None
    kind: BeliefKind
    subject: str | None = Field(default=None, description="e.g. 'thu', a reporter token")
    label: str = Field(description="Deterministic display label, e.g. 'Misses Thursdays'")
    state: BeliefState
    posterior: float = Field(ge=0, le=1)
    ci_low: float | None = None
    ci_high: float | None = None
    n_instances: int = 0
    first_seen: date
    confirmed_at: date | None = None
    retired_at: date | None = None
    retired_reason: str | None = None
    evidence: list[CitationRef] = Field(default_factory=list, description="From belief_evidence")


class BeliefDetail(Belief):
    transitions: list[tuple[int, BeliefState]] = Field(default_factory=list, description="[(day, state)]")
    contradicting: list[CitationRef] = Field(default_factory=list)


class BeliefPin(CMModel):
    """Belief lifecycle pin for the Lens slider."""

    belief_id: UUID
    kind: BeliefKind
    label: str
    transitions: list[tuple[int, BeliefState]]


class Conflict(CMModel):
    """A reconciler conflict (row of ``conflicts``). Produced by ``reconcile_frame`` (M3)."""

    conflict_id: UUID
    patient_id: UUID
    rule: RuleId
    tier: Tier
    title: str = Field(description="Deterministic rule text, e.g. 'Refill gap while self-reporting Taken'")
    evidence_ids: list[str] = Field(default_factory=list, description="Citation refs ('E:uuid', ...)")
    evidence: list[CitationRef] = Field(default_factory=list)
    opened_as_of: date
    closed_as_of: date | None = None


class ConflictDetail(Conflict):
    explanation: str = Field(description="Deterministic rule explanation, no LLM")
    approval_ids: list[UUID] = Field(default_factory=list)


class Driver(CMModel):
    """One risk driver: ``contribution_j = beta_j (x_j - mean_j)``; top 3 positive."""

    feature: str
    contribution: float
    belief_id: UUID | None = None
    label: str | None = None


class RiskScore(CMModel):
    """Risk for one patient-day (row of ``risk_scores``).

    ``p`` is the **dropout14** head (displayed): P(a run of >= 7 consecutive true misses
    inside d+1..d+14). ``p_miss7`` is the second head (M4): P(>= 2 true misses in d+1..d+7).
    CIs are 5th/95th percentiles of 500 Monte Carlo draws. Ranks follow-up only, never diagnosis.
    """

    patient_id: UUID | None = None
    as_of: date | None = None
    day: int | None = None
    p: float = Field(ge=0, le=1)
    ci_low: float = Field(ge=0, le=1)
    ci_high: float = Field(ge=0, le=1)
    p_miss7: float | None = Field(default=None, ge=0, le=1)
    miss7_ci_low: float | None = Field(default=None, ge=0, le=1)
    miss7_ci_high: float | None = Field(default=None, ge=0, le=1)
    drivers: list[Driver] = Field(default_factory=list, max_length=5)
    model_version: str


# ---------------------------------------------------------------------------
# Snapshot / Lens
# ---------------------------------------------------------------------------


class TrustLine(CMModel):
    """Reporter trust (from reporter_trust beliefs)."""

    reporter: Literal["self", "supporter", "family"]
    reporter_token: str | None = None
    score: float = Field(ge=0, le=1)
    ci_low: float | None = None
    ci_high: float | None = None


class Coverage(CMModel):
    channels_active: list[ConsentSource] = Field(default_factory=list)
    events_count: int = 0
    excluded_sources: list[str] = Field(default_factory=list)


class MemorySnapshot(CMModel):
    """What the system knew about a patient on a given day (``GET /patients/{pid}/memory?day=``)."""

    patient_id: UUID
    patient_token: str | None = None
    as_of: date
    sim_day: int
    features: FeatureVector
    beliefs: list[Belief] = Field(default_factory=list, description="Retired ones included (struck through)")
    conflicts: list[Conflict] = Field(default_factory=list)
    risk: RiskScore | None = Field(default=None, description="None before day 3")
    unknowns: list[str] = Field(default_factory=list)
    coverage: Coverage
    trust: list[TrustLine] = Field(default_factory=list)
    headline: str = Field(description="Deterministic template, e.g. 'Not enough history yet'")
    recommendation: str | None = Field(default=None, description="Only from an approved card for that day; never a fresh LLM call")
    computed: Literal["stored", "what_if"] = "stored"


class LensDiff(CMModel):
    new_beliefs: list[UUID] = Field(default_factory=list)
    retired_beliefs: list[UUID] = Field(default_factory=list)
    new_conflicts: list[UUID] = Field(default_factory=list)
    risk_delta: float | None = None
    ci_width_delta: float | None = None
    unknowns_delta: int = 0


class LensComparison(CMModel):
    a: MemorySnapshot
    b: MemorySnapshot
    diff: LensDiff


class FunnelSeries(CMModel):
    """Risk + CI over days (parallel arrays). The day-3 interval is wide; it narrows."""

    days: list[int]
    p: list[float]
    ci_low: list[float]
    ci_high: list[float]
    p_miss7: list[float | None] = Field(default_factory=list)
    excluded_sources: list[str] = Field(default_factory=list)


class TimelineItem(CMModel):
    """One lane item: an event, belief transition or decision."""

    id: str
    lane: Literal["patient", "supporter", "chemist", "lab", "portal", "doctor", "wearable", "belief", "system"]
    kind: str = Field(description="Event type, 'BeliefTransition', 'ContactScreened', ...")
    day: int
    occurred_at: datetime
    recorded_at: datetime | None = None
    label: str
    status: str | None = None
    citation: CitationRef


# ---------------------------------------------------------------------------
# Narration
# ---------------------------------------------------------------------------


class EvidenceEvent(CMModel):
    """A citable event inside an EvidenceBundle (tokenised, no PII)."""

    ref: str = Field(description="'E:{event_id}'")
    type: str
    day: int
    source: EventSource
    reporter_mode: ReporterMode
    fields: dict = Field(default_factory=dict, description="Tokenised payload fields the narrator may quote")


class EvidenceBundle(CMModel):
    """The ONLY input the narrator may state facts from (L2, as_of-valid)."""

    patient_token: str
    as_of: date
    sim_day: int
    beliefs: list[Belief] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    risk: RiskScore | None = None
    events_cited: list[EvidenceEvent] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    guideline_refs: list[CitationRef] = Field(default_factory=list, description="G refs (P1)")


class NarrationRequest(CMModel):
    patient_id: UUID
    as_of: date
    audience: Literal["doctor", "supporter"]
    question: str | None = None


class Sentence(CMModel):
    """One card sentence and the refs that justify it (>= 1 ref or it is cut)."""

    text: str
    refs: list[str] = Field(default_factory=list, description="'E:uuid', 'B:uuid', 'C:uuid', 'R:P-0042@60', 'G:uuid', 'D:uuid'")


class NarrationDraft(CMModel):
    """Structured LLM output of the narrator ``draft`` node."""

    sentences: list[Sentence]


class ValidatorCut(CMModel):
    idx: int
    text: str
    reason: Literal["no_ref", "unknown_ref", "not_as_of_valid", "number_mismatch", "banned_term", "over_length"]
    detail: str | None = None


class ValidatorReport(CMModel):
    """Cite-or-cut result. Template fallback if < 60% survive or a number mismatch remains after the retry."""

    sentences_in: int
    sentences_kept: int
    cut_ratio: float = Field(ge=0, le=1)
    cuts: list[ValidatorCut] = Field(default_factory=list)
    number_mismatches: int = 0
    banned_terms: list[str] = Field(default_factory=list)
    word_count: int = 0
    retried: bool = False
    fallback_used: bool = False
    passed: bool


class MemoryCard(CMModel):
    """<=120-word card (row of ``memory_cards``). Goes only to ``submit_for_review``."""

    card_id: UUID | None = None
    patient_id: UUID
    as_of: date
    audience: Literal["doctor", "supporter"]
    body: str
    sentences: list[Sentence]
    cut_ratio: float = Field(ge=0, le=1)
    fallback_used: bool = False
    status: Literal["draft", "approved", "rejected"] = "draft"
    approval_id: UUID | None = None
    validator_report: ValidatorReport | None = None


# ---------------------------------------------------------------------------
# Nightly
# ---------------------------------------------------------------------------


class NightlyReport(CMModel):
    """Summary of one ``cm-nightly`` run."""

    as_of: date
    run_id: UUID | None = None
    patients: int
    beliefs_changed: int
    conflicts_opened: int
    conflicts_closed: int = 0
    enqueued: int
    failures: list[str] = Field(default_factory=list, description="patient tokens that failed")
    duration_s: float


__all__ = [
    "IN_MEMORY_RISK_COLUMNS", "IN_MEMORY_BELIEF_COLUMNS", "CitationRef", "FeatureVector", "Detection", "Belief",
    "BeliefDetail", "BeliefPin", "Conflict", "ConflictDetail", "Driver", "RiskScore", "TrustLine", "Coverage",
    "MemorySnapshot", "LensDiff", "LensComparison", "FunnelSeries", "TimelineItem", "EvidenceEvent",
    "EvidenceBundle", "NarrationRequest", "Sentence", "NarrationDraft", "ValidatorCut", "ValidatorReport",
    "MemoryCard", "NightlyReport", "Audience",
]
