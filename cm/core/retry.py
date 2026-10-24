"""Retry, error classification, rate limiting and fallback (CLAUDE.md rule 12, INTEGRATION_DECISIONS C28).

Never retries spend_cap (402 / quota), auth (401/403) or invalid (400/422/validation) errors.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")

_SPEND_WORDS = ("insufficient_quota", "insufficient balance", "billing", "spend cap", "spend_cap", "quota exceeded")


@dataclass(frozen=True)
class Classified:
    error_class: str  # retryable | spend_cap | auth | invalid | unknown (task_runs.error_class)
    status: int | None = None
    retry_after: float | None = None


def _status(exc: BaseException) -> int | None:
    for obj in (exc, getattr(exc, "response", None)):
        for attr in ("status_code", "status"):
            v = getattr(obj, attr, None)
            if isinstance(v, int):
                return v
    return None


def _retry_after(exc: BaseException) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None) or getattr(exc, "headers", None) or {}
    try:
        for k, v in dict(headers).items():
            if str(k).lower() == "retry-after":
                return max(float(v), 0.0)
    except (TypeError, ValueError):
        return None
    return getattr(exc, "retry_after", None)


def classify(exc: BaseException) -> Classified:
    """Map any provider/library exception to an error_class."""
    declared = getattr(exc, "error_class", None)
    status, ra = _status(exc), _retry_after(exc)
    if declared in {"retryable", "spend_cap", "auth", "invalid", "unknown"}:
        return Classified(declared, status, ra)
    text = f"{type(exc).__name__} {exc}".lower()
    if status == 402 or any(w in text for w in _SPEND_WORDS):
        return Classified("spend_cap", status, ra)  # also a 429 whose body says quota
    if status in (401, 403):
        return Classified("auth", status, ra)
    if status in (400, 404, 413, 422) or isinstance(exc, (ValueError, TypeError)):
        return Classified("invalid", status, ra)
    if status == 429 or (status is not None and 500 <= status <= 599):
        return Classified("retryable", status, ra)
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return Classified("retryable", status, ra)
    return Classified("unknown", status, ra)


def is_retryable(exc: BaseException) -> bool:
    return classify(exc).error_class == "retryable"


class ProviderCallFailed(Exception):
    def __init__(self, error_class: str, attempts: int, cause: BaseException) -> None:
        super().__init__(f"provider call failed ({error_class}) after {attempts} attempt(s)")
        self.error_class, self.attempts, self.__cause__ = error_class, attempts, cause


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay: float = 0.5
    max_delay: float = 20.0
    max_total_wait: float = 45.0


def call_with_retry(fn: Callable[[], T], policy: RetryPolicy = RetryPolicy(), *,
                    sleep: Callable[[float], None] = time.sleep,
                    rand: Callable[[], float] = random.random) -> T:
    waited, attempt = 0.0, 0
    while True:
        attempt += 1
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            c = classify(exc)
            if c.error_class != "retryable" or attempt >= policy.max_attempts:
                raise ProviderCallFailed(c.error_class, attempt, exc) from exc
            backoff = min(policy.max_delay, policy.base_delay * 2 ** (attempt - 1))
            delay = c.retry_after if c.retry_after is not None else backoff * (0.5 + rand() / 2)
            if waited + delay > policy.max_total_wait:
                raise ProviderCallFailed(c.error_class, attempt, exc) from exc
            sleep(delay)
            waited += delay


def call_with_fallback(primary: Callable[[], T], fallback: Callable[[], T] | None, *,
                       allow_fallback: Callable[[], bool] = lambda: True,
                       policy: RetryPolicy = RetryPolicy(),
                       sleep: Callable[[float], None] = time.sleep) -> T:
    """Retry primary; fail over only for the retryable class and only if allow_fallback() (spend ceiling)."""
    try:
        return call_with_retry(primary, policy, sleep=sleep)
    except ProviderCallFailed as e:
        if e.error_class != "retryable" or fallback is None or not allow_fallback():
            raise
    return call_with_retry(fallback, policy, sleep=sleep)


class TokenBucket:
    def __init__(self, per_minute: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity, self.rate, self._clock = float(per_minute), per_minute / 60.0, clock
        self.level, self._t = float(per_minute), clock()

    def _refill(self) -> None:
        t = self._clock()
        self.level = min(self.capacity, self.level + (t - self._t) * self.rate)
        self._t = t

    def wait_time(self, n: float) -> float:
        self._refill()
        return 0.0 if self.level >= min(n, self.capacity) else (min(n, self.capacity) - self.level) / self.rate

    def take(self, n: float) -> None:
        self._refill()
        self.level -= min(n, self.capacity)

    def utilisation(self) -> float:
        self._refill()
        return 1.0 - self.level / self.capacity


class RateLimiter:
    """RPM and TPM buckets. ``acquire`` sleeps until both have room."""

    def __init__(self, rpm: float, tpm: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.rpm, self.tpm, self._sleep = TokenBucket(rpm, clock), TokenBucket(tpm, clock), sleep

    def acquire(self, tokens: int) -> float:
        wait = max(self.rpm.wait_time(1), self.tpm.wait_time(tokens))
        if wait > 0:
            self._sleep(wait)
        self.rpm.take(1)
        self.tpm.take(tokens)
        return wait

    def utilisation(self) -> float:
        return max(self.rpm.utilisation(), self.tpm.utilisation())


def _unused(*_: Any) -> None:  # keeps Any import used for typing consumers
    return None
