"""Lane F: Telegram client errors and an in-memory fake. A real httpx client implements ports.TelegramClient."""

from __future__ import annotations

from typing import Any


class TgError(Exception):
    pass


class TgRetryAfter(TgError):
    def __init__(self, seconds: float) -> None:
        super().__init__(f"retry after {seconds}s")
        self.seconds = seconds


class TgAuthError(TgError):
    """401/404 bad token. Never retried."""


class TgBlocked(TgError):
    """403 bot blocked by the user. Not a consent withdrawal."""


class TgTransient(TgError):
    """5xx or timeout; retryable."""


class FakeTelegramClient:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.edits: list[dict[str, Any]] = []
        self.script: list[Exception] = []  # one popped per send_message call
        self._n = 0

    async def send_message(
        self, chat_id: str, text: str, reply_markup: dict[str, Any] | None = None
    ) -> str:
        if self.script:
            raise self.script.pop(0)
        self._n += 1
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return str(1000 + self._n)

    async def edit_reply_markup(
        self, chat_id: str, message_id: str, reply_markup: dict[str, Any] | None
    ) -> None:
        self.edits.append(
            {"chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup}
        )
