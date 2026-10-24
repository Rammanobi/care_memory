"""Lane M: fallback order when a channel is down or over quota. Pure; never withdraws consent."""

from __future__ import annotations

from collections.abc import Iterable

# Preferred order. "portal" is the web inbox, always available and needing no external provider.
DEFAULT_ORDER: tuple[str, ...] = ("telegram", "gmail", "web_inbox")


def degrade_order(preferred: Iterable[str] | None = None, *, down: Iterable[str] = (),
                  over_quota: Iterable[str] = (), consented: Iterable[str] | None = None) -> list[str]:
    """Channels to try, in order. Down or over-quota channels are dropped; unconsented ones too.

    web_inbox is kept as the last resort when consented (or when consent is not supplied).
    """
    skip = set(down) | set(over_quota)
    allowed = None if consented is None else set(consented)
    order = list(preferred) if preferred else list(DEFAULT_ORDER)
    if "web_inbox" not in order:
        order.append("web_inbox")
    return [c for c in order if c not in skip and (allowed is None or c in allowed)]


def next_channel(tried: Iterable[str], **kw: Iterable[str]) -> str | None:
    t = set(tried)
    for c in degrade_order(**kw):  # type: ignore[arg-type]
        if c not in t:
            return c
    return None
