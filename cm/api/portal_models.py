"""Lane G: slice-level API models the frozen contracts do not define (see contracts/CHANGES.md RFC-S1).

Covers the patient/Supporter self-service app, the UI-shaped patient list/detail (the memory engine
tables are not populated in this slice), evidence, notes, messages, requests and usage. They extend the
contracts; they never replace a contract model that exists.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from cm.contracts.domain import CMModel
from cm.contracts.review import ReviewItem

Base = Literal["red", "amb", "grn"]
Level = Literal["red", "amb", "grn", "blu"]
CLINIC_AREA = {"anantapur": "Urban", "kalyandurg": "Rural", "dharmavaram": "Semi-urban"}


# ---- doctor console: patients ------------------------------------------------------------
class ChangeOut(CMModel):
    text: str
    ev: str = Field(description="Evidence ref shown as a chip, e.g. E-0412")


class UiPatient(CMModel):
    """One row of the patient list; field meanings match web/src/api/types.ts Patient."""

    patient_id: UUID
    person_id: UUID = Field(description="Use with /consents/{person_id}")
    token: str
    code: str = Field(description="Display code, e.g. PT-0142")
    sex: Literal["M", "F"]
    age: int
    day: int = Field(description="Treatment day at as_of")
    base: Base
    tag: str
    why: str
    missed: list[int] = Field(
        default_factory=list, description="Indexes 0..19 of missed days in the last 20"
    )
    no_data: int = 0
    next_step: str
    clinic: str = Field(description="Clinic slug, e.g. anantapur")
    visit_this_week: bool = False
    quiet: bool = False
    next_visit: str
    supporter: Literal["Linked", "Not linked"]
    consent: str
    changes: list[ChangeOut] = Field(default_factory=list)
    level: Level = Field(description="Derived row colour (blu = asked, grn after handled)")
    level_tag: str
    needs_me: bool = False
    has_request: bool = False
    open_reviews: int = 0


class EvidenceOut(CMModel):
    id: str = Field(description="E-0412, B-0101, C-0201, R-0301")
    event_id: UUID | None = None
    code: str
    at: str
    kind: Literal["dose", "refill", "visit", "message", "supporter", "lab", "system"]
    reporter: str
    text: str
    why: str


class NoteOut(CMModel):
    id: str
    code: str
    at: str
    by: str
    text: str


class NoteIn(CMModel):
    text: str = Field(min_length=1, max_length=500)


class MessageOut(CMModel):
    id: UUID
    src_id: UUID | None = Field(default=None, description="approval id")
    code: str
    at: datetime
    channel: str
    text: str
    approved_by: str
    version: int
    status: Literal["sent", "seen", "pending"]
    delivery: Literal["queued", "sent", "failed"] = Field(
        default="queued", description="Outbox row state: pending/sending=queued, sent, failed"
    )
    delivery_error: str | None = Field(default=None, description="Short reason when failed")


class AuditRowOut(CMModel):
    id: int
    code: str | None = None
    at: datetime
    actor: str
    role: str
    action: str
    label: str
    src_id: str | None = None
    version: int | None = None
    note: str | None = None


class TimelineEntryOut(CMModel):
    id: str
    event_id: UUID
    day: int
    occurred_at: datetime
    recorded_at: datetime
    type: str
    kind: str
    source: str
    text: str
    ref: str | None = None


class LensSnapOut(CMModel):
    code: str
    day: Literal[3, 60]
    known: str
    beliefs: list[dict[str, str]] = Field(default_factory=list)
    risk: tuple[int, int]
    conflicts: list[dict[str, str]] = Field(default_factory=list)


class PatientDetailOut(CMModel):
    patient: UiPatient
    evidence: list[EvidenceOut] = Field(default_factory=list)
    notes: list[NoteOut] = Field(default_factory=list)
    pending_reviews: list[ReviewItem] = Field(default_factory=list)
    requests: list[RequestOut] = Field(default_factory=list)
    messages: list[MessageOut] = Field(default_factory=list)
    lens: list[LensSnapOut] = Field(default_factory=list)
    as_of: datetime


class ClinicOut(CMModel):
    clinic_id: UUID
    id: str = Field(description="slug")
    name: str
    area: str


class TilesOut(CMModel):
    all: int
    needs: int
    requests: int
    quiet: int
    visit: int
    red: int
    track: int
    pending_requests: int
    pending_approvals: int
    sim_day: int
    as_of: datetime


# ---- requests ---------------------------------------------------------------------------
RequestStatus = Literal["waiting", "approved", "declined"]


class RequestOut(CMModel):
    id: UUID = Field(description="approval_id")
    patient_code: str
    kind: str
    text: str
    when: datetime
    draft: str
    status: RequestStatus
    reply: str | None = None
    due_at: datetime
    refs: list[str] = Field(default_factory=list)
    archived: bool = False


# ---- admin / usage -----------------------------------------------------------------------
class UsageTask(CMModel):
    name: str
    spend: float
    pct: int
    flag: str


class UsageDay(CMModel):
    d: str
    spend: float


class UsageOut(CMModel):
    mode: Literal["GREEN", "AMBER", "RED"]
    today_spend: float
    today_cap: float
    budget_used: float
    budget: float
    days: list[UsageDay]
    tasks: list[UsageTask]
    retries: int
    breaker: int
    billing: float
    provider_pct: int


class UsageModeIn(CMModel):
    mode: Literal["GREEN", "AMBER", "RED"]


class SimDayIn(CMModel):
    sim_day: int = Field(ge=0, le=400)


# ---- patient / Supporter portal ------------------------------------------------------------
class SupporterRef(CMModel):
    name: str
    relation: str


class PortalMe(CMModel):
    patient_code: str
    name: str
    clinic: str
    day: int
    supporter: SupporterRef | None = None
    reminder: str
    pending_reminder: str | None = None
    consents: dict[str, bool]


class PortalToday(CMModel):
    today: Literal["none", "taken", "missed"]
    reason: str | None = None
    marked_by: Literal["self", "supporter"] | None = None
    streak: int
    next_visit: str | None = None
    history: str = Field(
        description="Last 60 days oldest first: o taken, m missed, f not yet recorded"
    )


class DoseIn(CMModel):
    status: Literal["taken", "missed"]
    reason: str | None = Field(default=None, max_length=120)


class Appointment(CMModel):
    id: str
    kind: Literal["visit", "lab"]
    title: str
    when: str
    place: str
    note: str | None = None


class RecordDay(CMModel):
    date: date
    status: Literal["taken", "missed", "none"]
    reason: str | None = None


class PortalRecord(CMModel):
    days: list[RecordDay]
    taken: int
    missed: int
    upcoming: list[Appointment] = Field(default_factory=list)
    past: list[Appointment] = Field(default_factory=list)


class PortalMessage(CMModel):
    id: UUID = Field(description="outbox_id")
    title: str
    text: str
    created_at: datetime
    read: bool
    for_supporter: bool = False


class PortalRequestIn(CMModel):
    text: str = Field(min_length=2, max_length=500)
    kind: str = Field(default="Other", max_length=40)


class ReminderRequestIn(CMModel):
    time: str = Field(pattern=r"^\d{1,2}:\d{2} (am|pm)$")


class PortalRequestOut(CMModel):
    id: UUID
    text: str
    kind: str
    when: datetime
    status: RequestStatus
    reply: str | None = None


class ConsentSwitches(CMModel):
    telegram: bool
    gmail: bool
    calendar: bool


class SupporterView(CMModel):
    patient_code: str
    patient_name: str
    supporter_name: str
    relation: str
    allowed: bool
    today: Literal["none", "taken", "missed"]
    marked_by: Literal["self", "supporter"] | None = None
    week: str = Field(description="Last 7 days oldest first: o, m or f")
    messages: list[PortalMessage] = Field(default_factory=list)


class SupporterAskIn(CMModel):
    text: str = Field(min_length=2, max_length=500)


class PortalDocument(CMModel):
    id: str
    title: str
    kind: Literal["visit_summary", "lab_slip", "letter", "other"]
    date: date
    summary: str


class PortalMedicine(CMModel):
    """Plain-language medicine row. Never a drug name (non-negotiable 5)."""

    id: str
    label: str
    when: str
    note: str | None = None


class DistrictClinic(CMModel):
    id: str
    name: str
    area: str
    patients: int | None
    adherence: int | None = Field(
        description="Mean share of the last 20 days with a dose logged, %"
    )
    quiet: int | None
    pending: int | None
    suppressed: list[str] = Field(
        default_factory=list, description="Fields hidden because 1 <= n < SMALL_CELL_THRESHOLD"
    )


class DistrictQuiet(CMModel):
    code: str
    clinic: str
    why: str
    adherence: int
    no_data: int


class DistrictOut(CMModel):
    as_of: datetime
    small_cell_threshold: int
    clinics: list[DistrictClinic]
    quiet_patients: list[DistrictQuiet]
    total_patients: int | None
    total_pending_approvals: int


PatientDetailOut.model_rebuild()
