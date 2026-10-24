"""DB invariant fixtures (caremem_test only; the root conftest forces DB_NAME). Reuses the integration
fixtures so approvals are built exactly like the decision tests build them."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from tests.integration.conftest import actors, make_approval  # noqa: F401  (pytest fixtures)


@pytest.fixture()
def raw(seeded_db: None) -> Iterator[psycopg.Connection]:
    """A direct connection whose work is always rolled back (no residue in caremem_test)."""
    from cm.core.db import connect_direct

    conn = connect_direct()
    assert conn.execute("SELECT current_database() AS d").fetchone()["d"] != "caremem"
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def expect_db_error(conn: psycopg.Connection, sql: str, args: Any = ()) -> psycopg.Error:
    """Run ``sql`` in a savepoint and return the error it must raise."""
    try:
        with conn.transaction():
            conn.execute(sql, args)
    except psycopg.Error as exc:
        return exc
    raise AssertionError(f"statement was allowed: {sql}")
