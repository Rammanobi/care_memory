"""Lane F: token buckets, 1 msg/s per chat plus a global cap. Time is injected so tests never sleep."""

from __future__ import annotations

from collections.abc import Callable


class TokenBucket:
    def __init__(self, rate: float, burst: float, now: Callable[[], float]) -> None:
        self.rate, self.burst, self._now = rate, burst, now
        self._tokens = burst
        self._at = now()

    def _refill(self) -> None:
        t = self._now()
        self._tokens = min(self.burst, self._tokens + (t - self._at) * self.rate)
        self._at = t

    def try_take(self) -> bool:
        self._refill()
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False

    def wait_seconds(self) -> float:
        self._refill()
        return 0.0 if self._tokens >= 1 else (1 - self._tokens) / self.rate


class ChatLimiter:
    """Per-chat bucket plus one global bucket. ``allow`` takes from both or neither."""

    def __init__(
        self, now: Callable[[], float], per_chat_rps: float = 1.0, global_rps: float = 20.0
    ) -> None:
        self._now, self._rps = now, per_chat_rps
        self._chats: dict[str, TokenBucket] = {}
        self._global = TokenBucket(global_rps, global_rps, now)

    def allow(self, chat_id: str) -> float:
        """0.0 when allowed (tokens taken), else seconds to wait."""
        b = self._chats.setdefault(chat_id, TokenBucket(self._rps, 1, self._now))
        w = max(b.wait_seconds(), self._global.wait_seconds())
        if w > 0:
            return w
        b.try_take()
        self._global.try_take()
        return 0.0
