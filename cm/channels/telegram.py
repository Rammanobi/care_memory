"""Lane F: Telegram channel facade. FastAPI route (lane G) calls ``handle_webhook``.

Reads env names only: TELEGRAM_WEBHOOK_SECRET (secret header), TELEGRAM_PER_CHAT_RPS, TELEGRAM_GLOBAL_RPS.
"""

from __future__ import annotations

import dataclasses
import os
import secrets
from typing import Any

from cm.channels.tg_inbound import Deps, handle_update, verify_secret
from cm.channels.tg_ratelimit import ChatLimiter

__all__ = ["handle_local_poll", "TelegramChannel", "handle_webhook", "verify_secret", "limiter_from_env"]


def handle_webhook(
    raw: dict[str, Any], header_secret: str | None, deps: Deps
) -> tuple[int, dict[str, Any]]:
    """Return (status, body) for POST /webhooks/telegram."""
    return handle_update(raw, header_secret, deps)


# Per-process random value held only in this module's memory, so an HTTP caller can never send it.
_LOCAL_POLL_KEY = secrets.token_hex(16)


def handle_local_poll(raw: dict[str, Any], deps: Deps) -> tuple[int, dict[str, Any]]:
    """Trusted path for the local poller (python -m cm.jobs.tg_poll). The poller authenticates by owning
    the bot token, so there is no secret header. Never import this from an HTTP route."""
    trusted = dataclasses.replace(deps, secret=_LOCAL_POLL_KEY, inline_files=True)
    return handle_update(raw, _LOCAL_POLL_KEY, trusted)


def limiter_from_env(now) -> ChatLimiter:  # noqa: ANN001
    return ChatLimiter(
        now,
        float(os.environ.get("TELEGRAM_PER_CHAT_RPS", "1")),
        float(os.environ.get("TELEGRAM_GLOBAL_RPS", "20")),
    )


class TelegramChannel:
    """Bundle of inbound deps for the route."""

    def __init__(self, deps: Deps) -> None:
        self.deps = deps

    def webhook(self, raw: dict[str, Any], header_secret: str | None) -> tuple[int, dict[str, Any]]:
        return handle_update(raw, header_secret, self.deps)
