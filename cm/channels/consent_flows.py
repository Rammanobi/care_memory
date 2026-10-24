"""Lane M: record/revoke channel consent and suppression checks used by the router (F11)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from cm.channels.ports_gmail import ConsentStore

PURPOSES = ("daily_checkin", "care_coordination", "supporter_sharing", "programme_monitoring")
_STOP = {"stop", "/stop", "unsubscribe", "withdraw"}


def record_consent(store: ConsentStore, person_id: UUID, source: str, purpose: str, now: datetime,
                   via: str = "console") -> None:
    store.append(person_id, source, purpose, "granted", via, now)


def revoke_consent(store: ConsentStore, person_id: UUID, source: str, now: datetime, via: str = "console",
                   purposes: tuple[str, ...] = PURPOSES) -> int:
    """Withdraw every purpose on a source. Append-only; returns rows written."""
    n = 0
    for p in purposes:
        if store.latest(person_id, source, p) == "granted":
            store.append(person_id, source, p, "withdrawn", via, now)
            n += 1
    return n


def is_suppressed(store: ConsentStore, person_id: UUID, source: str, purpose: str) -> bool:
    """True unless the latest state is an explicit grant (never or withdrawn both suppress)."""
    return store.latest(person_id, source, purpose) != "granted"


def handle_consent_command(text: str, person_id: UUID, source: str, store: ConsentStore, now: datetime) -> bool:
    """STOP-style command revokes the source. True when it was a consent command."""
    if text.strip().lower() not in _STOP:
        return False
    revoke_consent(store, person_id, source, now, via=source)
    return True
