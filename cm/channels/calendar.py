"""Lane M: Google Calendar visit events (F6). Only approved visit decisions create events."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
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


def sync_calendar_events(as_of: Any, *, api: CalendarApi | None = None, calendar_id: str | None = None,
                         list_approved: Callable[[Any], list[dict[str, Any]]] | None = None,
                         consent_of: Callable[[Any], tuple[str | None, bool]] | None = None) -> dict[str, int]:
    """Job skeleton for /tasks/calendar-sync (task kind ``calendar_sync``).

    Reads approved/edited visit decisions decided at or before ``as_of`` and upserts one event each via
    ``create_visit_event`` (deterministic id, so re-runs update). The approval payload carries the event in
    ``payload['calendar_event']`` (a CalendarEventSpec dict); rows without one are skipped. ``api`` is the
    real GoogleCalendarApi only when wired by the integrator; with none given this is a dry run (counts only).
    ``consent_of(patient_id) -> (email, consents)`` supplies the optional attendee.
    """
    if list_approved is None:
        from cm.store import gmail_repo

        list_approved = gmail_repo.approved_visit_decisions
    out = {"seen": 0, "upserted": 0, "skipped": 0, "dry_run": 0}
    for row in list_approved(as_of):
        out["seen"] += 1
        raw = (row.get("payload") or {}).get("calendar_event")
        if not raw:
            out["skipped"] += 1
            continue
        spec = CalendarEventSpec.model_validate(raw)
        if api is None or not calendar_id:
            out["dry_run"] += 1
            continue
        email, consents = consent_of(row["patient_id"]) if consent_of else (None, False)
        eid = create_visit_event(spec, patient_id=row["patient_id"], calendar_id=calendar_id, api=api,
                                 approved=True, approval_id=row["approval_id"], patient_email=email,
                                 patient_consents=consents)
        out["upserted" if eid else "skipped"] += 1
    return out
