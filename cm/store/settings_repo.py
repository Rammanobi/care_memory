"""Lane A: settings table with optimistic locking and a 60 s read cache."""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from cm.core.db import transaction

_TTL_S = 60.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class VersionConflict(Exception):
    """Raised when expected_version does not match the stored version."""


def clear_cache() -> None:
    _cache.clear()


def get_setting(key: str, as_of: Any = None, *, conn: Any = None) -> dict[str, Any] | None:
    """Return {'value','version','updated_at','updated_by'} or None.

    `as_of` is accepted for API symmetry: settings are current-state, not bitemporal.
    """
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _TTL_S:
        return hit[1]
    if conn is None:
        with transaction() as c:
            return get_setting(key, as_of, conn=c)
    row = conn.execute(
        "SELECT value, version, updated_at, updated_by FROM cm.settings WHERE key=%s", (key,)
    ).fetchone()
    if row:
        _cache[key] = (time.monotonic(), row)
    return row


def set_setting(
    key: str,
    value: Any,
    *,
    expected_version: int | None,
    updated_by: UUID | None,
    updated_at: Any = None,
    conn: Any = None,
) -> dict[str, Any]:
    """Insert (expected_version None) or update with an optimistic lock."""
    if conn is None:
        with transaction() as c:
            return set_setting(
                key,
                value,
                expected_version=expected_version,
                updated_by=updated_by,
                updated_at=updated_at,
                conn=c,
            )
    _cache.pop(key, None)
    if expected_version is None:
        row = conn.execute(
            "INSERT INTO cm.settings (key, value, updated_by, updated_at) "
            "VALUES (%s,%s,%s,COALESCE(%s, now())) ON CONFLICT (key) DO NOTHING "
            "RETURNING value, version, updated_at, updated_by",
            (key, Jsonb(value), updated_by, updated_at),
        ).fetchone()
    else:
        row = conn.execute(
            "UPDATE cm.settings SET value=%s, version=version+1, updated_by=%s, "
            "updated_at=COALESCE(%s, now()) WHERE key=%s AND version=%s "
            "RETURNING value, version, updated_at, updated_by",
            (Jsonb(value), updated_by, updated_at, key, expected_version),
        ).fetchone()
    if row is None:
        raise VersionConflict(key)
    return row
