"""Lane A: ids and idempotency keys."""

from __future__ import annotations

import uuid

_NS = uuid.UUID("5d1f0a3e-8a47-4f0a-9d2b-0c3a4e7b6f10")


def new_id() -> uuid.UUID:
    return uuid.uuid4()


def det_id(*parts: str) -> uuid.UUID:
    """Deterministic uuid5 from parts (seed data)."""
    return uuid.uuid5(_NS, "|".join(parts))


def idempotency_key(*parts: str) -> str:
    """Stable key `a:b:c`; the events table requires 3..255 characters."""
    key = ":".join(str(p) for p in parts)
    if not 3 <= len(key) <= 255:
        raise ValueError("idempotency key must be 3..255 characters")
    return key
