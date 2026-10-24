"""API contracts: common envelopes, ingest, webhooks, channel payloads, worker task bodies, Supporter, PWA, mock portal.

FROZEN at ``contracts-v1``. No ``/v1`` prefix on any route (Z5). Errors are :class:`Problem`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import ConfigDict, Field

from .domain import (
    AgeBand,
    CMModel,
    ConsentSource,
    ContactSymptoms,
    MonthStr,
    OutboundChannel,
    PaymentStatus,
    Relation,
    SupporterVisitMode,
)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------


class Problem(CMModel):
    """RFC 7807-style error body."""

    type: str = "about:blank"
    title: str
    detail: str | None = None
    status: int | None = None
    code: str | None = Field(default=None, description="already_decided, reason_required, banned_term, forbidden_scope, red_not_bulk, seed_in_train, ...")


class Page(CMModel, Generic[T]):
    """Cursor pagination wrapper."""

    items: list[T]
    next_cursor: str | None = None
    total: int | None = None


LiveTopic = Literal["review", "tasks", "sim", "channels", "eval", "settings", "outbox"]


class LiveEvent(CMModel):
    """SSE payload of ``GET /stream`` (ids only; clients refetch)."""

    seq: int
    topic: LiveTopic
    type: str = Field(description="e.g. approval.created, approval.decided, task.state, sim.clock, outbox.sent")
    entity_id: str | None = None
    patient_id: UUID | None = None
    clinic_id: UUID | None = None
    district_id: UUID | None = None
    state: str | None = None
    at: datetime


class HealthOut(CMModel):
    status: Literal["ok", "degraded", "down"]
    db: bool | None = None
    store: bool | None = None
    version: str | None = None


class OkOut(CMModel):
    ok: bool = True


class TaskRef(CMModel):
    """Returned when a route starts a job/task (202)."""

    task_id: str


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


class IngestError(CMModel):
    row: int | None = None
    field: str | None = None
    message: str


class IngestReceipt(CMModel):
    accepted: int = 0
    rejected: int = 0
    unmatched: int = 0
    duplicates: int = 0
    event_ids: list[UUID] = Field(default_factory=list)
    review_items: list[UUID] = Field(default_factory=list, description="approval_ids raised (identity, fast-path Red, ...)")
    task_id: str | None = None
    errors: list[IngestError] = Field(default_factory=list)


class LabResultIn(CMModel):
    """``POST /ingest/lab`` (structured, no vision). Fast-path R2."""

    patient_id: UUID | None = None
    nikshay_id: str | None = None
    lab_id: str | None = None
    test: Literal["smear", "cbnaat", "truenat", "culture", "other"]
    result: str
    rif_resistant: bool | None = None
    report_date: date
    lab_ref: str = Field(description="Lab's own report id; key lab:{sha256(lab_ref+patient)}")


class SupporterCheckinIn(CMModel):
    """``POST /ingest/supporter`` (web fallback for one-tap check-ins)."""

    patient_id: UUID
    mode: SupporterVisitMode
    client_uuid: UUID = Field(description="Idempotency: web:{client_uuid}")
    occurred_at: datetime | None = None
    approval_id: UUID | None = Field(default=None, description="Visit list approval")
    pill_count: int | None = Field(default=None, ge=0, le=500)
    weight: float | None = Field(default=None, ge=25, le=150)
    symptoms: list[str] = Field(default_factory=list)
    payment: PaymentStatus | None = None


class HcRecord(CMModel):
    """One Health Connect record (P1)."""

    record_type: str
    start: datetime
    end: datetime | None = None
    value: float
    unit: str


class WearableBatchIn(CMModel):
    """``POST /ingest/wearable`` (P1, service token)."""

    patient_id: UUID
    records: list[HcRecord] = Field(max_length=2000)


class PortalPaymentIn(CMModel):
    nikshay_id: str
    month: MonthStr
    amount: int = Field(ge=0)
    status: Literal["paid", "pending", "failed", "unpaid"]
    paid_on: date | None = None
    pfms_ref: str | None = None


class PortalRegistrationIn(CMModel):
    nikshay_id: str
    notified_on: date
    facility_code: str
    treatment_start: date


class PortalIngestIn(CMModel):
    """``POST /ingest/portal`` body (service token)."""

    payments: list[PortalPaymentIn] = Field(default_factory=list)
    registrations: list[PortalRegistrationIn] = Field(default_factory=list)


class ChemistCsvRow(CMModel):
    """One parsed chemist CSV line (known headers; unknown headers go to intake)."""

    bill_no: str | None = None
    line_no: int | None = None
    sold_on: date
    patient_name: str | None = Field(default=None, description="Used only by the identity resolver; never stored in events")
    phone_last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    nikshay_id: str | None = None
    drug_code: str | None = None
    tablets: int = Field(ge=0)
    days_supply: int | None = None
    row_sha1: str


class HouseholdContactIn(CMModel):
    """``POST /ingest/household-contact`` (assigned Supporter or doctor)."""

    patient_id: UUID
    contact_id: UUID | None = Field(default=None, description="None = new contact (action 'listed')")
    action: Literal["listed", "screened", "referred", "declined"] = "listed"
    relation: Relation | None = None
    age_band: AgeBand | None = None
    name: str | None = Field(default=None, max_length=120, description="Encrypted under the patient's DEK; never in events")
    symptoms: ContactSymptoms | None = None
    contact_agreed: bool | None = None
    note: str | None = Field(default=None, max_length=300)
    client_uuid: UUID


class HouseholdContactOut(CMModel):
    """A ``household_contacts`` row. ``display_name`` only for the treating doctor / assigned Supporter."""

    contact_id: UUID
    patient_id: UUID
    relation: Relation | None = None
    age_band: AgeBand | None = None
    display_name: str | None = None
    symptoms: ContactSymptoms = Field(default_factory=ContactSymptoms)
    flagged: bool
    screened_at: datetime | None = None
    referred: bool = False
    doctor_decision: Literal["refer_test", "tpt_decided", "no_action"] | None = None
    decided_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class LabField(CMModel):
    name: str
    value: str | None = None
    confidence: float = Field(ge=0, le=1)


class LabReportExtraction(CMModel):
    """P1 vision extraction. Always needs a doctor confirm (approval kind lab_confirm)."""

    upload_sha256: str
    gcs_uri: str
    fields: list[LabField]
    test: Literal["smear", "cbnaat", "truenat", "culture", "other"] | None = None
    rif_resistant: bool | None = None
    report_date: date | None = None
    overall_confidence: float = Field(ge=0, le=1)
    extraction_model: str


# ---------------------------------------------------------------------------
# Webhooks and channels
# ---------------------------------------------------------------------------


class PubSubMessage(CMModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    data: str = Field(description="base64 JSON {emailAddress, historyId}")
    message_id: str | None = Field(default=None, alias="messageId")
    publish_time: datetime | None = Field(default=None, alias="publishTime")
    attributes: dict[str, str] = Field(default_factory=dict)


class PubSubPush(CMModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    message: PubSubMessage
    subscription: str | None = None


class GmailNotification(CMModel):
    """Decoded ``PubSubPush.message.data``."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    email_address: str = Field(alias="emailAddress")
    history_id: int = Field(alias="historyId")


class GmailFetchIn(CMModel):
    """Body of ``/tasks/gmail-fetch`` (task ``gmail-fetch-{historyId}``)."""

    mailbox: str
    history_id: int


class TelegramUpdate(CMModel):
    """Subset of a Telegram ``Update``; unknown fields are kept."""

    model_config = ConfigDict(extra="allow")
    update_id: int
    message: dict[str, Any] | None = None
    callback_query: dict[str, Any] | None = None
    my_chat_member: dict[str, Any] | None = None


class TgCallback(CMModel):
    """Parsed ``callback_data`` (<= 64 bytes). ``prompt`` = outbox_id as 32 hex chars."""

    kind: Literal["c", "s", "pay", "stop", "hh", "v"]
    prompt: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    value: str | None = None
    mask: int | None = None
    index: int | None = None


class CalendarEventSpec(CMModel):
    """Calendar event written via the outbox (``channel=calendar``)."""

    kind: Literal["refill", "test", "visit", "family_screen"]
    summary: str = Field(description="Neutral wording; banned-term checked")
    start: datetime
    end: datetime
    attendee_person_id: UUID
    color_id: str | None = None
    extended: dict[str, str] = Field(default_factory=dict)


class ChannelProfile(CMModel):
    """Cached in ``patients.channel_profile``; recomputed on consent or unreachable events."""

    patient_id: UUID | None = None
    active_sources: list[ConsentSource] = Field(default_factory=list)
    mode: Literal["full", "daily_checkin", "supporter_only", "records_only", "paused"]
    fallback_order: list[OutboundChannel] = Field(default_factory=list)
    degraded_reasons: list[str] = Field(default_factory=list)
    as_of: date | None = None


# ---------------------------------------------------------------------------
# Worker task bodies (cm-worker, OIDC only)
# ---------------------------------------------------------------------------


class CheckinsTaskIn(CMModel):
    as_of: date
    slot: Literal["morning", "evening", "proxy"] = "morning"


class CheckinNudgeIn(CMModel):
    outbox_id: UUID = Field(description="The unanswered check-in prompt (task nudge-{outbox_id})")


class DigestTaskIn(CMModel):
    doctor_id: UUID | None = None


class VisitListsTaskIn(CMModel):
    date: date


class DrainOutboxIn(CMModel):
    channel: OutboundChannel | None = None


class EmptyTaskIn(CMModel):
    """Body of gmail-watch-renew / gmail-sweep."""


class PortalSyncIn(CMModel):
    as_of: date


class CalendarSyncIn(CMModel):
    as_of: date
    kinds: list[Literal["refill", "test", "visit", "family_screen"]] = Field(default_factory=lambda: ["family_screen"])


class DistrictReportTaskIn(CMModel):
    district_id: UUID
    month: MonthStr


# ---------------------------------------------------------------------------
# Supporter
# ---------------------------------------------------------------------------


class VisitItem(CMModel):
    patient_id: UUID
    patient_token: str
    display_name: str | None = Field(default=None, description="Assigned Supporter only")
    kind: Literal["visit", "family_screen"] = "visit"
    brief: str = Field(description="Doctor-approved Supporter brief (no medical claims)")
    reason_chips: list[str] = Field(default_factory=list)
    priority: int = 0


class VisitList(CMModel):
    """``GET /supporter/{sid}/visit-list`` (approved only)."""

    supporter_id: UUID
    date: date
    approval_id: UUID | None = None
    items: list[VisitItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# PWA (P1)
# ---------------------------------------------------------------------------


class MagicLinkExchangeIn(CMModel):
    token: str = Field(min_length=16, max_length=256)


class PwaInboxItem(CMModel):
    outbox_id: UUID
    body: str
    buttons: list[dict[str, str]] = Field(default_factory=list)
    created_at: datetime


class PwaInbox(CMModel):
    items: list[PwaInboxItem] = Field(default_factory=list)


class PwaCheckinIn(CMModel):
    prompt_outbox_id: UUID | None = None
    status: Literal["taken", "missed", "unwell"]
    client_uuid: UUID


class PwaSymptomsIn(CMModel):
    items: list[int] = Field(default_factory=list)
    client_uuid: UUID


class PwaMonthlyIn(CMModel):
    month: MonthStr
    payment: PaymentStatus | None = None
    weight: float | None = Field(default=None, ge=25, le=150)
    client_uuid: UUID


class PushSubscriptionIn(CMModel):
    endpoint: str
    keys: dict[str, str] = Field(description="{p256dh, auth}")


# ---------------------------------------------------------------------------
# Mock Ni-kshay portal (P0, lane K)
# ---------------------------------------------------------------------------


class MockNikshayPatient(CMModel):
    nikshay_id: str
    facility_code: str
    notified_on: date
    treatment_start: date
    patient_token: str | None = None


class MockNikshayPayment(CMModel):
    nikshay_id: str
    month: MonthStr
    amount: int
    status: Literal["paid", "pending", "failed", "unpaid"]
    paid_on: date | None = None
    pfms_ref: str | None = None


class MockScenarioIn(CMModel):
    scenario: Literal["payment_failed", "payment_delayed", "late_registration", "reset"]
    nikshay_id: str | None = None
    month: MonthStr | None = None


__all__ = [
    "Problem", "Page", "LiveTopic", "LiveEvent", "HealthOut", "OkOut", "TaskRef", "IngestError", "IngestReceipt",
    "LabResultIn", "SupporterCheckinIn", "HcRecord", "WearableBatchIn", "PortalPaymentIn", "PortalRegistrationIn",
    "PortalIngestIn", "ChemistCsvRow", "HouseholdContactIn", "HouseholdContactOut", "LabField",
    "LabReportExtraction", "PubSubMessage", "PubSubPush", "GmailNotification", "GmailFetchIn", "TelegramUpdate",
    "TgCallback", "CalendarEventSpec", "ChannelProfile", "CheckinsTaskIn", "CheckinNudgeIn", "DigestTaskIn",
    "VisitListsTaskIn", "DrainOutboxIn", "EmptyTaskIn", "PortalSyncIn", "CalendarSyncIn", "DistrictReportTaskIn",
    "VisitItem", "VisitList", "MagicLinkExchangeIn", "PwaInboxItem", "PwaInbox", "PwaCheckinIn", "PwaSymptomsIn",
    "PwaMonthlyIn", "PushSubscriptionIn", "MockNikshayPatient", "MockNikshayPayment", "MockScenarioIn",
]
