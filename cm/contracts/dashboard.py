"""Dashboard contracts: patient list/detail, clinic and district aggregates (tier 2).

FROZEN at ``contracts-v1``. Officer-facing counts use :class:`SuppressedInt`
(1 <= n <= 4 is suppressed). STS/DTO never see names or patient-level rows except
:class:`PaymentStuckRow` tokens.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from .api import HouseholdContactOut
from .domain import (
    CMModel,
    ConsentSource,
    EventSource,
    PatientStatus,
    Phase,
    ReporterMode,
    RuleId,
    Tier,
)
from .memory import Belief, CitationRef, Conflict, MemoryCard, RiskScore
from .review import ReviewItem

# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------


class SparkPoint(CMModel):
    day: int
    verified: float | None = Field(default=None, description="Rolling 7-day, witnessed + record")
    self_report: float | None = None


class FlagChip(CMModel):
    rule: RuleId
    tier: Tier
    label: str = Field(description="R6 label is 'Contacts not screened'")


class ChannelChip(CMModel):
    channel: ConsentSource
    consent: Literal["granted", "withdrawn", "never"]
    enabled: bool = Field(description="Global kill switch (settings channels.*.enabled)")


class PatientSummary(CMModel):
    patient_id: UUID
    token: str
    display_name: str | None = Field(default=None, description="Treating doctor only")
    treatment_day: int
    phase: Phase
    status: PatientStatus = "active"
    tier: Tier
    risk: RiskScore | None = Field(default=None, description="None before day 3")
    adherence_28d: float | None = None
    spark: list[SparkPoint] = Field(default_factory=list)
    flags: list[FlagChip] = Field(default_factory=list)
    open_reviews: int = 0
    last_contact_at: datetime | None = None
    channels: list[ChannelChip] = Field(default_factory=list)
    supporter_token: str | None = None


class HouseholdSummary(CMModel):
    """``GET /patients/{pid}/household``. Names only for the treating doctor and assigned Supporter."""

    patient_id: UUID
    listed: int
    screened: int
    referred: int
    flagged: int = Field(description="Under-5 or symptomatic")
    due_by_day: int = 14
    overdue: bool
    declined: bool = False
    contacts: list[HouseholdContactOut] = Field(default_factory=list)


class PatientDetail(CMModel):
    summary: PatientSummary
    regimen: str
    treatment_start: date
    as_of: date
    card: MemoryCard | None = Field(default=None, description="Latest approved at or before as_of")
    card_draft_approval_id: UUID | None = None
    conflicts: list[Conflict] = Field(default_factory=list)
    beliefs: list[Belief] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    pending_reviews: list[ReviewItem] = Field(default_factory=list)
    household: HouseholdSummary | None = None


class AdherencePoint(CMModel):
    day: int
    r7: float | None = None
    r14: float | None = None
    r28: float | None = None
    decayed: float | None = None
    r7_self: float | None = None


class CalendarCell(CMModel):
    day: int
    weekday: str
    status: Literal["taken", "missed", "no_reply", "unknown"]
    reporter_mode: ReporterMode | None = None


class WeekdayCell(CMModel):
    weekday: str
    misses: int
    total: int
    posterior_effect: float | None = None


class RefillGap(CMModel):
    from_day: int
    to_day: int
    taps_during: int
    conflict_id: UUID | None = None


class RefillSeries(CMModel):
    pills_on_hand: list[tuple[int, float]] = Field(default_factory=list)
    dispenses: list[tuple[int, int]] = Field(default_factory=list)
    taken_taps: list[int] = Field(default_factory=list)
    gaps: list[RefillGap] = Field(default_factory=list)


class PatientSeries(CMModel):
    """Read from ``features_daily`` (no recompute)."""

    as_of: date
    adherence: list[AdherencePoint] = Field(default_factory=list)
    calendar: list[CalendarCell] = Field(default_factory=list)
    weekday: list[WeekdayCell] = Field(default_factory=list)
    refill: RefillSeries = Field(default_factory=RefillSeries)
    reply_minutes: list[tuple[int, float | None]] = Field(default_factory=list)
    change_points: list[int] = Field(default_factory=list)
    weight: list[tuple[int, float]] = Field(default_factory=list)


class EventOut(CMModel):
    """``GET /events/{event_id}`` (citation click-through, role-checked)."""

    event_id: UUID
    patient_id: UUID
    type: str
    source: EventSource
    sim_day: int
    occurred_at: datetime
    recorded_at: datetime
    reporter_token: str | None = None
    reporter_mode: ReporterMode | None = None
    channel: str | None = None
    consent_id: UUID | None = None
    payload_display: dict = Field(default_factory=dict, description="Tokenised")
    raw_excerpt: str | None = Field(default=None, description="Doctor only")
    supersedes: UUID | None = None
    cited_by: list[CitationRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Clinic and district
# ---------------------------------------------------------------------------


class SuppressedInt(CMModel):
    value: int | None = Field(description="None when suppressed")
    suppressed: bool = Field(default=False, description="True when 1 <= n <= 4")


class ClinicSummary(CMModel):
    clinic_id: UUID
    as_of: date
    patients_by_tier: dict[Tier, int]
    open_reviews: dict[Tier, int]
    sla: dict[Tier, float | None] = Field(description="Median minutes to decision")
    overdue_reviews: int = 0
    visits_due: int
    acceptance_rate: float | None = None
    contacts_screened_pct: float | None = None


class DistrictSummary(CMModel):
    district_id: UUID
    as_of: date
    active: SuppressedInt
    verified_adherence_7d: float | None = None
    self_reported_adherence_7d: float | None = None
    refill_gaps: SuppressedInt
    payments_overdue_60d: SuppressedInt
    red_open: SuppressedInt
    median_review_minutes: dict[Tier, float | None]
    supporter_visits: dict[Literal["planned", "done"], int]
    consent_coverage: float | None = None
    high_risk: SuppressedInt
    red_over_4h: SuppressedInt
    contacts_listed: SuppressedInt
    contacts_screened: SuppressedInt
    contacts_screened_pct: float | None = Field(default=None, description="None if listed < 5")
    contacts_referred: SuppressedInt
    patients_contacts_overdue: SuppressedInt
    deltas_7d: dict[str, float | None] = Field(default_factory=dict)


class BlockRow(CMModel):
    block_id: UUID
    block_name: str = Field(description="Neutral: 'Block A'")
    patients: SuppressedInt
    high_risk: SuppressedInt
    red_open: SuppressedInt
    payments_overdue: SuppressedInt
    visits_done: int
    visits_planned: int
    contacts_screened_pct: float | None = None
    verified_adherence_7d: float | None = None


class TrendSeries(CMModel):
    metric: str = Field(description="e.g. verified_adherence_7d, contacts_screened_pct")
    days: list[int]
    values: list[float | None]


class PaymentStuckRow(CMModel):
    block_name: str
    patient_token: str = Field(description="Never a name")
    months_affected: list[str]
    oldest_age_days: int
    bucket: Literal["30-59", "60-89", "90+"]
    evidence: list[CitationRef] = Field(default_factory=list)


class CascadeStage(CMModel):
    """P1."""

    stage: Literal["diagnosed", "notified", "started", "end_intensive", "completed"]
    count: SuppressedInt
    pct_of_previous: float | None = None
    in_progress: bool = False


class PharmacyRow(CMModel):
    """P1."""

    pharmacy_token: str
    block_name: str
    csv_last_recorded_at: datetime | None = None
    median_lateness_days: float | None = None
    dispenses: SuppressedInt
    dispenses_unregistered: SuppressedInt
    unregistered_share: float | None = None
    stale: bool


class SupporterActivityRow(CMModel):
    """P1."""

    supporter_token: str
    block_name: str
    planned: int
    done: int
    witnessed_share: float | None = None
    unreachable_rate: float | None = None
    families_screened: int = 0


class MonthlyReport(CMModel):
    """P1 (merges 01's DistrictMonthlyReport)."""

    district_id: UUID
    month: str
    generated_at: datetime
    summary: DistrictSummary
    cascade: list[CascadeStage] = Field(default_factory=list)
    blocks: list[BlockRow] = Field(default_factory=list)
    payments_stuck: list[PaymentStuckRow] = Field(default_factory=list)
    pharmacies: list[PharmacyRow] = Field(default_factory=list)
    supporters: list[SupporterActivityRow] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RevealIn(CMModel):
    """P1, DTO only, audited."""

    patient_token: str
    reason: str = Field(min_length=10, max_length=300)


class RevealOut(CMModel):
    patient_token: str
    display_name: str
    clinic_id: UUID
    audit_id: int


__all__ = [
    "SparkPoint", "FlagChip", "ChannelChip", "PatientSummary", "HouseholdSummary", "PatientDetail",
    "AdherencePoint", "CalendarCell", "WeekdayCell", "RefillGap", "RefillSeries", "PatientSeries", "EventOut",
    "SuppressedInt", "ClinicSummary", "DistrictSummary", "BlockRow", "TrendSeries", "PaymentStuckRow",
    "CascadeStage", "PharmacyRow", "SupporterActivityRow", "MonthlyReport", "RevealIn", "RevealOut",
]
