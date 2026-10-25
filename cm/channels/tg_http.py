"""Integration: real Telegram Bot API client (httpx). Implements ports.TelegramClient.

The bot token is read from the environment at call time only. It is never stored on the object, never
logged, and never put in an exception message (the URL contains it, so every httpx error is rewrapped).
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx

from cm.channels.tg_client import TgAuthError, TgBlocked, TgError, TgRetryAfter, TgTransient
from cm.core.retry import ProviderCallFailed, RetryPolicy, call_with_retry

# httpx logs every request URL at INFO and the URL contains the bot token: keep it quiet.
for _n in ("httpx", "httpcore"):
    logging.getLogger(_n).setLevel(logging.WARNING)

API = "https://api.telegram.org"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
FILE_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
FILE_POLICY = RetryPolicy(max_attempts=3, base_delay=0.5, max_delay=4.0, max_total_wait=10.0)
DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024


def _token() -> str:
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not tok:
        raise TgAuthError("TELEGRAM_BOT_TOKEN is not set")
    return tok


class TgConflict(TgTransient):
    """409: a webhook is set or another getUpdates consumer is running."""


class TgFileError(TgError):
    """A getFile or file download failed. ``error_class`` feeds cm.core.retry. The message never holds the
    URL or the token (the URL contains the token), so it is safe to log."""

    def __init__(self, reason: str, *, error_class: str = "invalid", retry_after: float | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.error_class = error_class
        self.retry_after = retry_after


class TgFileTooLarge(TgFileError):
    """The file is, or grew past, the byte limit (declared sizes can lie, so the stream is counted)."""


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

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport  # tests inject httpx.MockTransport; never the real network
        self._sleep = sleep

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
        self,
        chat_id: str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        reply_to_message_id: int | None = None,
    ) -> str:
        body: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup:
            body["reply_markup"] = reply_markup
        if reply_to_message_id is not None:
            body["reply_to_message_id"] = int(reply_to_message_id)
            body["allow_sending_without_reply"] = True  # the original may be deleted: still deliver
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


    # ---- file download (sync, used from the handler thread; retries through cm.core.retry) ----------------

    def get_file(self, file_id: str) -> dict[str, Any]:
        """Bot API getFile -> {file_id, file_unique_id, file_size, file_path}. Raises TgFileError only."""

        def once() -> dict[str, Any]:
            url = f"{API}/bot{_token()}/getFile"
            try:
                with httpx.Client(timeout=TIMEOUT, transport=self._transport) as c:
                    r = c.post(url, json={"file_id": file_id})
            except httpx.TimeoutException:
                raise TgFileError("telegram timeout", error_class="retryable") from None
            except httpx.HTTPError as exc:
                raise TgFileError(
                    f"telegram network error: {type(exc).__name__}", error_class="retryable"
                ) from None
            try:
                data = r.json()
            except ValueError:
                data = None
            _check_file_status(r.status_code, data)
            res = (data or {}).get("result")
            if not isinstance(res, dict) or not res.get("file_path"):
                raise TgFileError("getFile returned no path")
            return res

        return self._with_retry(once)

    def download_file(self, file_path: str, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> bytes:
        """GET the file bytes. The stream is counted and cut off past ``max_bytes`` (TgFileTooLarge)."""
        if not file_path or file_path.startswith("/") or ".." in file_path.split("/"):
            raise TgFileError("bad file path")

        def once() -> bytes:
            url = f"{API}/file/bot{_token()}/{quote(file_path)}"
            buf = bytearray()
            try:
                with (
                    httpx.Client(timeout=FILE_TIMEOUT, transport=self._transport) as c,
                    c.stream("GET", url) as r,
                ):
                    if r.status_code != 200:
                        _check_file_status(r.status_code, None)
                    for chunk in r.iter_bytes():
                        buf += chunk
                        if len(buf) > max_bytes:
                            raise TgFileTooLarge("file larger than the limit")
            except httpx.TimeoutException:
                raise TgFileError("telegram timeout", error_class="retryable") from None
            except httpx.HTTPError as exc:
                raise TgFileError(
                    f"telegram network error: {type(exc).__name__}", error_class="retryable"
                ) from None
            return bytes(buf)

        return self._with_retry(once)

    def fetch_file(self, file_id: str, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> bytes:
        """getFile then download. Raises TgFileError (or TgFileTooLarge), never anything holding the token."""
        meta = self.get_file(file_id)
        size = meta.get("file_size")
        if isinstance(size, int) and size > max_bytes:
            raise TgFileTooLarge("file larger than the limit")
        return self.download_file(str(meta["file_path"]), max_bytes)

    def _with_retry(self, fn: Callable[[], Any]) -> Any:
        try:
            return call_with_retry(fn, FILE_POLICY, sleep=self._sleep)
        except ProviderCallFailed as exc:
            cause = exc.__cause__
            if isinstance(cause, TgFileError):
                raise cause from None
            raise TgFileError("file fetch failed", error_class=exc.error_class) from None
        except TgAuthError:
            raise TgFileError("bot token rejected", error_class="auth") from None


def _check_file_status(status: int, data: dict[str, Any] | None) -> None:
    """Map a non-ok reply of getFile or the file download to TgFileError (messages carry no URL)."""
    data = data or {}
    if status == 200 and (data.get("ok") or not data):
        return
    code = int(data.get("error_code") or status)
    if code == 429:
        ra = float((data.get("parameters") or {}).get("retry_after", 1))
        raise TgFileError("telegram rate limit", error_class="retryable", retry_after=ra)
    if code in (401, 403):
        raise TgFileError("bot token rejected", error_class="auth")
    if code >= 500 or code == 409:
        raise TgFileError(f"telegram {code}", error_class="retryable")
    raise TgFileError(f"telegram error {code}")  # 400 "file is too big", 404: retrying cannot help


async def admin_call(method: str, body: dict[str, Any]) -> dict[str, Any]:
    """Used by the setWebhook script only. Same error mapping; returns the Bot API result."""
    return await HttpTelegramClient()._call(method, body)
