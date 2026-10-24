"""Lane M: Google Calendar visit events (F6). Only approved visit decisions create events."""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from cm.channels.ports_gmail import CalendarApi, has_banned_term
from cm.contracts.api import CalendarEventSpec


def event_id(kind: str, patient_id: UUID | str, day: str) -> str:
    """Deterministic Calendar id: 32 hex chars (base32hex-legal), so a re-run upserts."""
    return hashlib.sha256(f"cal:{kind}:{patient_id}:{day}".encode()).hexdigest()[:32]


def build_event_body(spec: CalendarEventSpec, *, patient_email: str | None = None, patient_consents: bool = False,
                     duration_min: int = 30) -> dict[str, Any]:
    """Neutral wording only. The patient is added as attendee only when consent says so."""
    if has_banned_term(spec.summary) or any(has_banned_term(v) for v in spec.extended.values()):
        raise ValueError("banned term in calendar text")
    body: dict[str, Any] = {
        "summary": spec.summary,
        "start": {"dateTime": spec.start.isoformat()},
        "end": {"dateTime": spec.end.isoformat()},
        "guestsCanSeeOtherGuests": False,
        "guestsCanInviteOthers": False,
        "reminders": {"useDefault": True},
    }
    if spec.extended:
        body["extendedProperties"] = {"private": dict(spec.extended)}
    if patient_consents and patient_email:
        body["attendees"] = [{"email": patient_email}]
    return body


def create_visit_event(spec: CalendarEventSpec, *, patient_id: UUID | str, calendar_id: str, api: CalendarApi,
                       approved: bool, approval_id: UUID | None = None, patient_email: str | None = None, patient_consents: bool = False) -> str | None:
    """Idempotent upsert. Refuses (None) unless the visit decision is approved."""
    if spec.kind not in ("visit", "family_screen") or not approved or approval_id is None:
        return None
    eid = event_id(spec.kind, patient_id, spec.start.date().isoformat())
    body = build_event_body(spec, patient_email=patient_email, patient_consents=patient_consents)
    return api.upsert_event(calendar_id, eid, body)


def sync_calendar_events(as_of: Any) -> Any:  # job stub, wired by the integrator
    raise NotImplementedError("wire to /tasks/calendar-sync: list approved visit decisions, call create_visit_event")
