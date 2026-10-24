"""Domain contracts: shared Literal aliases, core entities and the L0 ``Event`` union.

FROZEN at ``contracts-v1``. Changes go through ``contracts/CHANGES.md``.

Every shared ``Literal`` alias lives here and is imported by the other contract
modules. Names follow INTEGRATION_DECISIONS.md (Z1-Z7): ``approval_id`` (never
``review_id``), ``recorded_at`` (never ``received_at``), the ``task_runs`` table.

Event storage convention
------------------------
Each concrete event class is *flat*: the envelope fields from :class:`EventBase`
map 1:1 onto ``cm.events`` columns, and every other field is the type-specific
payload. The repository stores ``model.model_dump(mode="json",
exclude=EVENT_ENVELOPE_FIELDS)`` in ``events.payload`` and rebuilds the model
with ``EventAdapter.validate_python({**row, **row["payload"]})``.

Names never go in event payloads (P0 privacy rule). People are referenced by
UUID or token only; PII lives in ``identity_vault`` / ``household_contacts.enc_name``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# ---------------------------------------------------------------------------
# Base model config
# ---------------------------------------------------------------------------


class CMModel(BaseModel):
    """Base for all contract models: forbid unknown fields, keep enum values as str."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, use_enum_values=True)


# ---------------------------------------------------------------------------
# Shared Literal aliases (import these everywhere; never redefine)
# ---------------------------------------------------------------------------

Role = Literal["patient", "supporter", "doctor", "chemist", "lab", "sts", "dto", "admin"]
"""``persons.role`` and the JWT ``role`` claim. ``patient`` signs in only via the P1 PWA magic link."""

ConsoleRole = Literal["doctor", "supporter", "sts", "dto", "admin", "chemist", "lab"]
"""Roles that can hold ``auth_credentials`` (username/password)."""

Tier = Literal["red", "amber", "green"]
"""Review / conflict urgency. Red: escalate to STS at 4 h, never auto-sent. Amber: 12:00 batch. Green: templates."""

ReporterMode = Literal["self", "witnessed", "told", "record"]
"""Who vouches for an event: the patient (self), a Supporter who saw it (witnessed),
a Supporter who was told (told), or a system/record feed (record)."""

DoseStatus = Literal["taken", "missed", "unwell", "unclear"]
"""``DoseCheckin.status``. Intake never infers ``taken`` from ambiguous text: the default is ``unclear``."""

ConsentSource = Literal[
    "telegram", "web", "supporter", "gmail", "calendar", "wearable", "chemist", "lab", "portal"
]
"""Data source a consent covers (``consents.source``)."""

EventSource = Literal[
    "telegram", "web", "supporter", "gmail", "calendar", "wearable", "chemist", "lab", "portal",
    "system", "console",
]
"""``events.source``: a :data:`ConsentSource` plus ``system`` (CheckinPrompt, rules) and ``console`` (doctor actions)."""

Purpose = Literal["daily_checkin", "care_coordination", "supporter_sharing", "programme_monitoring"]
"""DPDP purpose a consent is scoped to."""

ConsentStateValue = Literal["granted", "withdrawn"]
"""``consents.state``. Absent rows read as ``never`` in API views."""

OutboundChannel = Literal["telegram", "gmail", "webpush", "web_inbox", "calendar"]
"""``outbox.channel``: where a message is delivered."""

BindingChannel = Literal["telegram", "gmail", "web", "webpush"]
"""``channel_bindings.channel``."""

AgeBand = Literal["<5", "5-14", "15-59", "60+"]
"""Household contact age band. ``<5`` always flags the contact."""

Relation = Literal["spouse", "child", "parent", "sibling", "other"]
"""Household contact relation to the patient."""

Lang = Literal["en", "te", "hi"]
"""Template / UI language."""

Audience = Literal["doctor", "supporter", "patient", "sts"]
"""Who a rendered text is for. Supporter/patient text passes the banned-term filter (hard block)."""

Phase = Literal["intensive", "continuation", "completed"]
"""Treatment phase (``patients.phase``)."""

PatientStatus = Literal["active", "records_only", "paused", "completed", "erased"]
"""``patients.status``. ``records_only``/``paused`` follow full consent withdrawal (arch §4.2)."""

RuleId = Literal["R1", "R2", "R3", "R4", "R5", "R6"]
"""Reconciler rule ids. R6 = "Contacts not screened" (M8). Labels live in the UI, ids never change."""

BeliefKind = Literal["weekday_miss", "payday_miss", "reporter_trust", "reply_drift", "refill_gap", "weight_trend"]
"""``beliefs.kind``."""

BeliefState = Literal["hypothesis", "confirmed", "dormant", "retired"]
"""Belief lifecycle: hypothesis -> confirmed (>=4 instances, P(effect>+20pts)>=0.90) -> dormant (21 d) -> retired (42 d)."""

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

PaymentStatus = Literal["received", "not_received", "unsure"]
"""Patient/Supporter-reported DBT (Ni-kshay Poshan) payment status."""

SupporterVisitMode = Literal["witnessed", "told", "unreachable"]

RefLetter = Literal["E", "B", "C", "R", "G", "D"]
"""Citation ref type: E event, B belief, C conflict, R risk (``R:{patient_token}@{day}``),
G guideline chunk, D patient-document chunk (T18, C12)."""

EventType = Literal[
    "DoseCheckin", "SymptomReport", "SupporterVisit", "PillCount", "Dispense", "LabResult",
    "WeightReport", "PaymentReport", "PortalPayment", "PortalRegistration", "WearableReading",
    "ReviewDecisionEvent", "ContextNote", "IdentityLinked", "BeliefRetired", "Tombstone",
    "CheckinPrompt", "RegimenChange", "ChannelUnreachable", "HouseholdContactEvent", "ConsentEvent",
]
"""All 21 ``events.type`` values. Mirrors the CHECK constraint in ``0001_core.sql``."""

# Token patterns (persons.token). LLMs only ever see these.
PATIENT_TOKEN_PATTERN = r"^P-\d{4}$"
PERSON_TOKEN_PATTERN = r"^[PSDCLTXA]-\d{2,4}$"
"""P patient, S supporter, D doctor, C chemist, L lab, T sts, X dto, A admin."""

PatientToken = Annotated[str, Field(pattern=PATIENT_TOKEN_PATTERN, description="Patient token, e.g. P-0042")]
PersonToken = Annotated[str, Field(pattern=PERSON_TOKEN_PATTERN, description="Person token, e.g. S-07, D-02")]
MonthStr = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Calendar month YYYY-MM")]


# ---------------------------------------------------------------------------
# Core entities
# ---------------------------------------------------------------------------


class Person(CMModel):
    """A row of ``cm.persons``. PII is never here; it lives in ``identity_vault``."""

    person_id: UUID
    role: Role
    token: str = Field(pattern=PERSON_TOKEN_PATTERN, description="Pseudonymous token the LLM sees, e.g. P-0042, S-07, D-02")
    clinic_id: UUID | None = None
    district_id: UUID | None = None
    backup_for: UUID | None = Field(default=None, description="Doctor this person backs up (sweeper 36 h step)")


class Patient(CMModel):
    """A row of ``cm.patients`` joined with its person token."""

    patient_id: UUID
    person_id: UUID
    token: str = Field(pattern=PATIENT_TOKEN_PATTERN)
    clinic_id: UUID
    treatment_start: date
    regimen: str = Field(description="Current regimen code; R2 reads the latest RegimenChange event, not this cache")
    phase: Phase
    status: PatientStatus
    channel_profile: dict = Field(default_factory=dict, description="Cached ChannelProfile JSON (api.ChannelProfile)")
    nikshay_id: str | None = None


# ---------------------------------------------------------------------------
# Events (L0)
# ---------------------------------------------------------------------------


class EventBase(CMModel):
    """Envelope shared by every event; columns of ``cm.events`` (append-only, bitemporal).

    ``occurred_at`` is when it happened; ``recorded_at`` is when the system learned it.
    ``as_of(T)`` reads use ``occurred_at <= T AND recorded_at <= T`` (M2).
    """

    event_id: UUID = Field(default_factory=uuid4)
    patient_id: UUID
    type: EventType
    occurred_at: datetime
    recorded_at: datetime
    source: EventSource
    reporter_id: UUID | None = Field(default=None, description="persons.person_id of whoever reported it")
    reporter_mode: ReporterMode
    channel: str | None = Field(default=None, description="Concrete channel, e.g. telegram, web, csv, gmail")
    consent_id: UUID | None = Field(default=None, description="Authorising consent; NULL only for source=system/console")
    supersedes: UUID | None = Field(default=None, description="event_id this corrects (latest non-superseded wins)")
    idempotency_key: str = Field(
        max_length=255,
        description="UNIQUE. tg:{update_id} | web:{client_uuid} | gm:{gmail_message_id} | chem:{chemist_id}:{bill_no}:{line_no} "
        "| chem:{chemist_id}:sha1:{row_sha1} | lab:{sha256} | wear:{token}:{recordType}:{start} | nk:{nikshay_id}:{kind}:{month}:{status} "
        "| hh:{contact_id}:{action}:{client_uuid} | prompt:{outbox_id} | decision:{approval_id}",
    )
    sim_run_id: UUID | None = Field(default=None, description="sim_clock.run_id that generated it (sim data only)")


EVENT_ENVELOPE_FIELDS: frozenset[str] = frozenset(EventBase.model_fields.keys())
"""Fields stored as ``cm.events`` columns; everything else goes in ``payload``."""


class DoseCheckin(EventBase):
    """A dose report (patient tap, Supporter proxy, or parsed free text)."""

    type: Literal["DoseCheckin"] = "DoseCheckin"
    status: DoseStatus
    for_date: date = Field(description="The treatment day the report is about")
    reply_seconds: int | None = Field(default=None, ge=0, description="tapped_at - outbox.sent_at of the prompt")
    prompt_outbox_id: UUID | None = Field(default=None, description="Outbox row of the CheckinPrompt being answered")
    late: bool = False
    proxy: bool = Field(default=False, description="True when implied by a SupporterVisit")


class SymptomReport(EventBase):
    """Symptom checklist result. ``danger=True`` triggers the R4 Red fast-path."""

    type: Literal["SymptomReport"] = "SymptomReport"
    items: list[int] = Field(default_factory=list, description="Checklist indices 0-7 the patient ticked")
    codes: list[str] = Field(default_factory=list, description="Stable symptom codes, e.g. cough_blood, breathless")
    danger: bool = False


class SupporterVisit(EventBase):
    """A Supporter visit outcome (witnessed / told / unreachable)."""

    type: Literal["SupporterVisit"] = "SupporterVisit"
    mode: SupporterVisitMode
    visit_date: date
    approval_id: UUID | None = Field(default=None, description="Approved visit_list this visit belongs to")
    visit_kind: Literal["dose", "family_screen"] = "dose"


class PillCount(EventBase):
    """Tablets remaining in the strip, counted by a Supporter (feeds R1 refill coverage)."""

    type: Literal["PillCount"] = "PillCount"
    remaining_tablets: int = Field(ge=0, le=500)


class Dispense(EventBase):
    """A chemist dispense line (CSV). Chemist lag up to 3 days is expected."""

    type: Literal["Dispense"] = "Dispense"
    chemist_id: UUID | None = None
    bill_no: str | None = None
    line_no: int | None = None
    row_sha1: str | None = None
    drug_code: str | None = None
    tablets: int = Field(ge=0)
    days_supply: int | None = Field(default=None, ge=0)


class LabResult(EventBase):
    """A confirmed lab result. LLM-extracted values only become this after a doctor confirm."""

    type: Literal["LabResult"] = "LabResult"
    test: Literal["smear", "cbnaat", "truenat", "culture", "other"]
    result: str = Field(description="Normalised result code, e.g. smear_2plus, mtb_detected")
    rif_resistant: bool | None = Field(default=None, description="True drives R2 (Red) while regimen is first-line")
    report_date: date
    lab_ref: str | None = None
    upload_sha256: str | None = None
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    edited_fields: list[str] = Field(default_factory=list)


class WeightReport(EventBase):
    type: Literal["WeightReport"] = "WeightReport"
    kg: float = Field(ge=25, le=150)


class PaymentReport(EventBase):
    """Patient/Supporter-reported receipt of the monthly DBT support."""

    type: Literal["PaymentReport"] = "PaymentReport"
    month: MonthStr
    status: PaymentStatus


class PortalPayment(EventBase):
    """Ni-kshay (mock) portal payment record. Key ``nk:{nikshay_id}:pay:{month}:{status}``."""

    type: Literal["PortalPayment"] = "PortalPayment"
    nikshay_id: str
    month: MonthStr
    amount: int = Field(ge=0, description="INR")
    status: Literal["paid", "pending", "failed", "unpaid"]
    paid_on: date | None = None
    pfms_ref: str | None = None


class PortalRegistration(EventBase):
    """Ni-kshay registration (E4). Key ``nk:{nikshay_id}:reg``."""

    type: Literal["PortalRegistration"] = "PortalRegistration"
    nikshay_id: str
    notified_on: date
    facility_code: str
    treatment_start: date


class WearableReading(EventBase):
    """Mock wearable reading (P1). Only ever adds an 'ask' chip; never a clinical claim."""

    type: Literal["WearableReading"] = "WearableReading"
    record_type: str = Field(description="e.g. RestingHeartRate, Steps, SleepSession")
    start: datetime
    end: datetime | None = None
    value: float
    unit: str


class ReviewDecisionEvent(EventBase):
    """Mirror of a doctor decision (key ``decision:{approval_id}``), written by ``cm/review/decide.py``."""

    type: Literal["ReviewDecisionEvent"] = "ReviewDecisionEvent"
    approval_id: UUID
    decision_id: UUID
    action: Literal["approve", "edit", "reject", "expired"]
    via: Literal["console", "gmail", "sweeper"]
    kind: str = Field(description="review.ReviewKind of the approval")
    tier: Tier
    reason: str | None = None


class ContextNote(EventBase):
    """Free text or structured context (E7). Replaces the void ``FreeTextNote``.

    ``kind`` examples: ``patient_text``, ``household_declined`` (suppresses R6),
    ``rejection_reason``, ``channel_unreachable``. Text is always tokenised.
    """

    type: Literal["ContextNote"] = "ContextNote"
    origin: Literal["patient_text", "supporter_text", "doctor"]
    kind: str
    text_tokenised: str = ""
    needs_clarification: bool = False
    data: dict = Field(default_factory=dict, description="Structured note, e.g. {weekday:'thu', reason:'work', action:'supporter_brings_dose'}")


class IdentityLinked(EventBase):
    """A (reversible) link of an external record to this patient. Unlink = action 'unlink' + supersedes."""

    type: Literal["IdentityLinked"] = "IdentityLinked"
    action: Literal["link", "unlink"] = "link"
    source: Literal["chemist", "lab", "portal"]  # type: ignore[assignment]  # record feed being linked
    source_ref: str
    score: float = Field(ge=0, le=100)
    band: Literal["auto", "review", "none"]
    decided_by: UUID | None = Field(default=None, description="Doctor person_id for review-band confirms")


class BeliefRetired(EventBase):
    """Doctor-driven forgetting: a reject retires the belief at once."""

    type: Literal["BeliefRetired"] = "BeliefRetired"
    belief_id: UUID
    reason: str
    decision_id: UUID | None = None


class Tombstone(EventBase):
    """PII-free replacement written by ``cm.erase_person()`` (the only bypass of the INSERT-only trigger)."""

    type: Literal["Tombstone"] = "Tombstone"
    original_type: str
    erasure_request_id: UUID


class CheckinPrompt(EventBase):
    """Appended by the outbox drainer after each successful check-in send (E1).

    ``source="system"``, ``reporter_mode="record"``, key ``prompt:{outbox_id}``.
    R5, reply time and engagement drift read it.
    """

    type: Literal["CheckinPrompt"] = "CheckinPrompt"
    outbox_id: UUID
    channel: Literal["telegram", "webpush", "supporter_proxy"]  # type: ignore[assignment]  # stored in events.channel
    for_date: date
    sent_at: datetime


class RegimenChange(EventBase):
    """Regimen start/switch (E2). The seed writes one at treatment start; R2 reads the latest as of the lab ``recorded_at``."""

    type: Literal["RegimenChange"] = "RegimenChange"
    regimen_from: str | None = None
    regimen_to: str
    line: Literal["first", "second", "other"]
    effective_date: date
    prescriber_id: UUID | None = None


class ChannelUnreachable(EventBase):
    """Channel delivery failure (E3). Degrades the channel profile; NEVER withdraws consent."""

    type: Literal["ChannelUnreachable"] = "ChannelUnreachable"
    channel: OutboundChannel  # type: ignore[assignment]  # stored in events.channel
    reason: Literal["blocked", "gone", "invalid_grant", "other"]
    detail: str | None = None


class ContactSymptoms(CMModel):
    """Household contact screening symptoms. Any True flags the contact."""

    cough_2w: bool = False
    fever: bool = False
    weight_loss: bool = False
    night_sweats: bool = False


class HouseholdContactEvent(EventBase):
    """Household contact screening step (E5, P0). ``household_contacts`` is its projection.

    Names NEVER go here (only ``household_contacts.enc_name``). Key ``hh:{contact_id}:{action}:{client_uuid}``.
    Flag rule (deterministic): ``age_band == "<5" OR any(symptoms)``.
    """

    type: Literal["HouseholdContactEvent"] = "HouseholdContactEvent"
    contact_id: UUID
    action: Literal["listed", "screened", "flagged", "referred", "doctor_decision", "declined"]
    relation: Relation | None = None
    age_band: AgeBand | None = None
    symptoms: ContactSymptoms | None = None
    contact_agreed: bool | None = None
    doctor_decision: Literal["refer_test", "tpt_decided", "no_action"] | None = None
    note: str | None = None


class ConsentEvent(EventBase):
    """A consent change. Row of the ``consents`` ledger AND (E6) a member of the Event union for the timeline.

    When used purely as a ledger row the event envelope fields may be defaulted;
    ``patient_id`` is set only when the person is a patient.
    """

    type: Literal["ConsentEvent"] = "ConsentEvent"
    patient_id: UUID | None = None  # type: ignore[assignment]
    consent_id: UUID  # type: ignore[assignment]
    person_id: UUID
    source: ConsentSource  # type: ignore[assignment]  # stored in events.source / consents.source
    purpose: Purpose
    state: ConsentStateValue
    effective_at: datetime
    via: str = Field(pattern=r"^(console|telegram|web|paper|supporter:S-\d+)$")
    notice_version: str = "v1"


Event = Annotated[
    DoseCheckin | SymptomReport | SupporterVisit | PillCount | Dispense | LabResult | WeightReport | PaymentReport | PortalPayment | PortalRegistration | WearableReading | ReviewDecisionEvent | ContextNote | IdentityLinked | BeliefRetired | Tombstone | CheckinPrompt | RegimenChange | ChannelUnreachable | HouseholdContactEvent | ConsentEvent,
    Field(discriminator="type"),
]
"""Discriminated union of all L0 events, keyed on ``type``."""

EventAdapter: TypeAdapter[Event] = TypeAdapter(Event)
"""Validate/serialise an :data:`Event` from a dict (``EventAdapter.validate_python``)."""

EventList = TypeAdapter(list[Event])

__all__ = [
    "CMModel", "Role", "ConsoleRole", "Tier", "ReporterMode", "DoseStatus", "ConsentSource", "EventSource",
    "Purpose", "ConsentStateValue", "OutboundChannel", "BindingChannel", "AgeBand", "Relation", "Lang",
    "Audience", "Phase", "PatientStatus", "RuleId", "BeliefKind", "BeliefState", "Weekday", "PaymentStatus",
    "SupporterVisitMode", "RefLetter", "EventType", "PatientToken", "PersonToken", "MonthStr",
    "PATIENT_TOKEN_PATTERN", "PERSON_TOKEN_PATTERN",
    "Person", "Patient", "EventBase", "EVENT_ENVELOPE_FIELDS", "DoseCheckin", "SymptomReport",
    "SupporterVisit", "PillCount", "Dispense", "LabResult", "WeightReport", "PaymentReport", "PortalPayment",
    "PortalRegistration", "WearableReading", "ReviewDecisionEvent", "ContextNote", "IdentityLinked",
    "BeliefRetired", "Tombstone", "CheckinPrompt", "RegimenChange", "ChannelUnreachable", "ContactSymptoms",
    "HouseholdContactEvent", "ConsentEvent", "Event", "EventAdapter", "EventList",
]
