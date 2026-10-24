"""Integration: real Telegram Bot API client (httpx). Implements ports.TelegramClient.

The bot token is read from the environment at call time only. It is never stored on the object, never
logged, and never put in an exception message (the URL contains it, so every httpx error is rewrapped).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from cm.channels.tg_client import TgAuthError, TgBlocked, TgRetryAfter, TgTransient

# httpx logs every request URL at INFO and the URL contains the bot token: keep it quiet.
for _n in ("httpx", "httpcore"):
    logging.getLogger(_n).setLevel(logging.WARNING)

API = "https://api.telegram.org"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _token() -> str:
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not tok:
        raise TgAuthError("TELEGRAM_BOT_TOKEN is not set")
    return tok


class TgConflict(TgTransient):
    """409: a webhook is set or another getUpdates consumer is running."""


REPLY_METHODS = {"sendMessage", "answerCallbackQuery", "editMessageReplyMarkup"}


def map_response(status: int, data: dict[str, Any] | None) -> None:
    """Raise the mapped Tg* error for a non-ok Bot API reply. Returns None when ok."""
    data = data or {}
    if status == 200 and data.get("ok"):
        return
    code = int(data.get("error_code") or status)
    if code == 429:
        params = data.get("parameters") or {}
        raise TgRetryAfter(float(params.get("retry_after", 1)))
    if code == 403:
        raise TgBlocked("bot blocked or chat unavailable")
    if code in (401, 404):
        raise TgAuthError("bot token rejected")
    if code == 409:
        raise TgConflict("telegram conflict 409")
    if code >= 500:
        raise TgTransient(f"telegram {code}")
    raise TgTransient(f"telegram error {code}")  # 400s other than the above: not retried forever (attempt cap)


class HttpTelegramClient:
    """Async Bot API client. One short-lived httpx call per request; no state."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport  # tests inject httpx.MockTransport; never the real network

    async def _call(
        self, method: str, body: dict[str, Any], timeout: httpx.Timeout | None = None
    ) -> Any:
        url = f"{API}/bot{_token()}/{method}"
        try:
            async with httpx.AsyncClient(timeout=timeout or TIMEOUT, transport=self._transport) as c:
                r = await c.post(url, json=body)
        except httpx.TimeoutException:
            raise TgTransient("telegram timeout") from None
        except httpx.HTTPError as exc:
            raise TgTransient(f"telegram network error: {type(exc).__name__}") from None
        try:
            data = r.json()
        except ValueError:
            data = None
        map_response(r.status_code, data)
        res = (data or {}).get("result")
        return res if res is not None else {}

    async def send_message(
        self, chat_id: str, text: str, reply_markup: dict[str, Any] | None = None
    ) -> str:
        body: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup:
            body["reply_markup"] = reply_markup
        res = await self._call("sendMessage", body)
        return str(res.get("message_id", ""))

    async def edit_reply_markup(
        self, chat_id: str, message_id: str, reply_markup: dict[str, Any] | None
    ) -> None:
        body: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": int(message_id),
            "reply_markup": reply_markup or {"inline_keyboard": []},
        }
        await self._call("editMessageReplyMarkup", body)

    async def get_updates(self, offset: int | None, timeout_s: int = 25) -> list[dict[str, Any]]:
        """Long poll. The HTTP timeout is longer than the server-side wait."""
        body: dict[str, Any] = {"timeout": timeout_s, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            body["offset"] = offset
        res = await self._call("getUpdates", body, httpx.Timeout(timeout_s + 10.0, connect=5.0))
        return list(res) if isinstance(res, list) else []

    async def delete_webhook(self, drop_pending_updates: bool = False) -> None:
        await self._call("deleteWebhook", {"drop_pending_updates": drop_pending_updates})

    async def apply_reply(self, reply: dict[str, Any]) -> None:
        """Apply an inline webhook-style reply body ({"method": ..., ...}) as a real Bot API call."""
        body = dict(reply)
        method = body.pop("method", None)
        if method not in REPLY_METHODS:
            return
        await self._call(method, body)


async def admin_call(method: str, body: dict[str, Any]) -> dict[str, Any]:
    """Used by the setWebhook script only. Same error mapping; returns the Bot API result."""
    return await HttpTelegramClient()._call(method, body)
