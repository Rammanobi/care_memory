"""Admin contracts: auth, persons, settings, consent and erasure, audit (tier 2).

FROZEN at ``contracts-v1``.

Auth (P4): HS256 JWT signed with ``JWT_SIGNING_KEY``; claims
``{sub, role, person_id, clinic_id, district_id, tv, iat, exp, jti}``; TTL 480 min;
sent as the ``cm_session`` cookie and accepted as ``Authorization: Bearer``.
``tv`` must equal ``auth_credentials.token_version``. Passwords: ``hashlib.scrypt``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from .domain import (
    CMModel,
    ConsentEvent,
    ConsentSource,
    ConsentStateValue,
    ConsoleRole,
    Purpose,
    Role,
)

CONSENT_VIA_PATTERN = r"^(console|telegram|web|paper|supporter:S-\d+)$"

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class JwtClaims(CMModel):
    """Decoded session token claims."""

    sub: str
    role: Role
    person_id: UUID
    clinic_id: UUID | None = None
    district_id: UUID | None = None
    tv: int = Field(description="Must equal auth_credentials.token_version")
    iat: int
    exp: int
    jti: str


class LoginIn(CMModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)


class DemoSwitchIn(CMModel):
    """P1, DEMO_MODE only."""

    username: str = Field(max_length=64)


class TokenOut(CMModel):
    access_token: str = Field(description="Also set as the HttpOnly cm_session cookie")
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = 480 * 60
    role: Role


class Me(CMModel):
    person_id: UUID
    username: str | None = None
    token: str
    display_name: str | None = None
    role: Role
    clinic_id: UUID | None = None
    district_id: UUID | None = None
    demo_mode: bool = False
    offline: bool = False


# ---------------------------------------------------------------------------
# Persons
# ---------------------------------------------------------------------------


class PersonAdminOut(CMModel):
    person_id: UUID
    username: str | None = None
    display_name: str | None = None
    role: Role
    token: str
    clinic_id: UUID | None = None
    district_id: UUID | None = None
    backup_for: UUID | None = None
    active: bool
    last_login_at: datetime | None = None


class PersonAdminIn(CMModel):
    username: str = Field(pattern=r"^[a-z0-9._-]{3,32}$")
    display_name: str = Field(max_length=120)
    role: ConsoleRole
    clinic_id: UUID | None = None
    district_id: UUID | None = None
    backup_for: UUID | None = None
    initial_password: str | None = Field(default=None, min_length=8, max_length=128, description="Demo seeding only")


class PersonAdminPatch(CMModel):
    role: ConsoleRole | None = None
    active: bool | None = None
    clinic_id: UUID | None = None
    district_id: UUID | None = None
    backup_for: UUID | None = None


# ---------------------------------------------------------------------------
# Settings (settings table, optimistic lock on version)
# ---------------------------------------------------------------------------


class RuleThresholds(CMModel):
    """``settings['thresholds']``. Read by router, cm-sweeper and R6 via settings_repo (60 s cache)."""

    red_escalation_hours: float = Field(4, ge=1, le=24)
    amber_batch_time: str = Field("12:00", pattern=r"^\d{2}:\d{2}$")
    amber_reminder_hours: float = 24
    amber_backup_hours: float = 36
    approval_expiry_hours: float = Field(48, ge=12, le=168)
    green_sample_rate: float = Field(0.10, ge=0.05, le=1.0)
    risk_high: float = Field(0.50, ge=0.1, le=0.9)
    risk_medium: float = Field(0.25, ge=0.05, le=0.8)
    quiet_start: str = Field("21:00", pattern=r"^\d{2}:\d{2}$")
    quiet_end: str = Field("07:00", pattern=r"^\d{2}:\d{2}$")
    max_messages_per_recipient_day: int = Field(3, ge=1, le=10)
    max_redrafts: int = Field(2, ge=0, le=3)
    supporter_list_cap: int = Field(8, ge=1, le=20)
    contacts_due_day: int = Field(14, ge=7, le=30, description="R6 starts firing on this treatment day")
    r5_amber_streak: int = Field(3, ge=2, le=14)
    r5_red_streak: int = Field(7, ge=3, le=21)


class DetectorParams(CMModel):
    """Read-only in the UI (frozen in docs/maths.md)."""

    weekday_min_instances: int = 4
    weekday_min_posterior: float = 0.90
    weekday_min_effect: float = 0.20
    dormant_days: int = 21
    retired_days: int = 42


class SettingsOut(CMModel):
    version: int
    values: RuleThresholds
    detectors: DetectorParams
    channels: dict[str, bool] = Field(description="channels.{telegram|gmail|calendar|wearable}.enabled; supporter_web always on")
    updated_by: str | None = None
    updated_at: datetime | None = None


class SettingsIn(CMModel):
    version: int = Field(description="Must match current version (409 otherwise)")
    values: RuleThresholds


# ---------------------------------------------------------------------------
# Consent and erasure
# ---------------------------------------------------------------------------


class ConsentState(CMModel):
    person_id: UUID
    by_source_purpose: dict[str, dict[str, Literal["granted", "withdrawn", "never"]]]
    ledger: list[ConsentEvent] = Field(default_factory=list, description="Newest first")


class ConsentEventIn(CMModel):
    person_id: UUID
    source: ConsentSource
    purpose: Purpose
    state: ConsentStateValue
    via: str = Field(pattern=CONSENT_VIA_PATTERN)
    notice_version: str = "v1"


class ConsentEventOut(CMModel):
    consent_id: UUID
    person_id: UUID
    source: ConsentSource
    purpose: Purpose
    state: ConsentStateValue
    effective_at: datetime
    via: str
    notice_version: str
    event_id: UUID | None = Field(default=None, description="Mirrored ConsentEvent in events (patients only)")


ErasureStatus = Literal["awaiting_second_approval", "approved", "executing", "done", "rejected"]


class ErasureRequestIn(CMModel):
    person_id: UUID
    reason: str = Field(min_length=5, max_length=500)


class ErasureApproveIn(CMModel):
    """Second approver (must differ from requested_by; DB CHECK)."""

    approve: bool = True
    note: str | None = Field(default=None, max_length=300)


class ErasureRequestOut(CMModel):
    request_id: UUID
    person_id: UUID
    person_token: str | None = None
    reason: str
    status: ErasureStatus
    requested_by: UUID
    requested_at: datetime
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    executed_at: datetime | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Audit (P1)
# ---------------------------------------------------------------------------


class AuditEntry(CMModel):
    id: int
    at: datetime
    actor: str
    role: str
    action: str
    tool: str | None = None
    args_hash: str | None = None
    result_ids: list[str] = Field(default_factory=list)
    patient_token: str | None = None
    thread_id: str | None = None
    ip: str | None = None


__all__ = [
    "CONSENT_VIA_PATTERN", "JwtClaims", "LoginIn", "DemoSwitchIn", "TokenOut", "Me", "PersonAdminOut",
    "PersonAdminIn", "PersonAdminPatch", "RuleThresholds", "DetectorParams", "SettingsOut", "SettingsIn",
    "ConsentState", "ConsentEventIn", "ConsentEventOut", "ErasureStatus", "ErasureRequestIn", "ErasureApproveIn",
    "ErasureRequestOut", "AuditEntry",
]
