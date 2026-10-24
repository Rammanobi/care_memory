"""Lane A: shared psycopg pool. Sync API; routes are plain `def` so FastAPI runs them in a threadpool."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from cm.core.config import load_settings

_pool: ConnectionPool | None = None
_lock = threading.Lock()


def get_pool() -> ConnectionPool:
    """Return the process-wide pool (opened lazily)."""
    global _pool
    with _lock:
        if _pool is None:
            s = load_settings()
            _pool = ConnectionPool(
                s.dsn,
                min_size=s.pool_min,
                max_size=s.pool_max,
                kwargs={"row_factory": dict_row},
                open=True,
            )
        return _pool


def close_pool() -> None:
    global _pool
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None


@contextmanager
def transaction() -> Iterator[psycopg.Connection]:
    """One pooled connection inside one transaction (commit on success, rollback on error)."""
    with get_pool().connection() as conn:
        yield conn


def connect_direct() -> psycopg.Connection:
    """Standalone connection (migrations, tests); caller closes it."""
    return psycopg.connect(load_settings().dsn, row_factory=dict_row)


def ping() -> bool:
    try:
        with transaction() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False
