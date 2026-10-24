"""Lane F: deterministic router. Channel choice by consent and preference; degrade is lane M's.

Fallback order (feature spec F11): patient telegram -> webpush -> Supporter relay -> none;
Supporter telegram -> webpush -> web_inbox; doctor console always plus gmail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from cm.router.banned import find_banned
from cm.router.quiet_hours import in_quiet_hours

ORDER: dict[str, list[str]] = {
    "patient": ["telegram", "webpush", "supporter_relay"],
    "supporter": ["telegram", "webpush", "web_inbox"],
    "doctor": ["web_inbox", "gmail"],
}
CHANNEL_SOURCE = {
    "telegram": "telegram",
    "webpush": "web",
    "web_inbox": "web",
    "gmail": "gmail",
    "supporter_relay": "supporter",
}
PATIENT_FACING = {"patient", "supporter"}


@dataclass
class Decision:
    action: Literal["send", "defer", "block", "none"]
    channel: str | None = None
    reason: str | None = None


def choose_channel(
    role: str,
    consented: dict[str, bool],
    reachable: dict[str, bool] | None = None,
    preferred: str | None = None,
) -> str | None:
    """First channel in order that is consented and reachable; ``preferred`` is tried first."""
    order = list(ORDER.get(role, []))
    if preferred in order:
        order.remove(preferred)
        order.insert(0, preferred)
    for ch in order:
        if consented.get(ch) and (reachable is None or reachable.get(ch, True)):
            return ch
    return None


def route(
    role: str,
    text: str,
    now: datetime,
    consented: dict[str, bool],
    reachable: dict[str, bool] | None = None,
    preferred: str | None = None,
    red_to_staff: bool = False,
) -> Decision:
    """Banned terms first (hard block), then channel by consent, then quiet hours."""
    if role in PATIENT_FACING:
        terms = find_banned(text)
        if terms:
            return Decision("block", None, "banned_term:" + ",".join(terms))
    ch = choose_channel(role, consented, reachable, preferred)
    if ch is None:
        return Decision("none", None, "no_consent")
    if in_quiet_hours(now) and not red_to_staff:
        return Decision("defer", ch, "quiet_hours")
    return Decision("send", ch)
