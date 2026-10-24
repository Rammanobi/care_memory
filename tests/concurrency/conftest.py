"""Concurrency fixtures (caremem_test only). Reuses the integration fixtures for approvals and the
Telegram PG environment (throwaway patient P-9901, fake bot client, pinned clock)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest

from tests.integration.conftest import actors, make_approval  # noqa: F401  (pytest fixtures)
from tests.integration.test_telegram_pg import env  # noqa: F401  (pytest fixture)


def race(fns: list[Callable[[], Any]], timeout: float = 60) -> list[Any]:
    """Start every callable at the same instant (barrier) and return results or raised exceptions."""
    barrier = threading.Barrier(len(fns))
    out: list[Any] = [None] * len(fns)

    def run(i: int, fn: Callable[[], Any]) -> None:
        barrier.wait()
        try:
            out[i] = fn()
        except BaseException as exc:  # noqa: BLE001  (collected for the assertions)
            out[i] = exc

    threads = [threading.Thread(target=run, args=(i, f)) for i, f in enumerate(fns)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout)
        assert not t.is_alive(), "a racing thread hung (deadlock?)"
    return out


@pytest.fixture()
def second_doctor(actors: dict[str, Any]) -> UUID:  # noqa: F811
    """A second doctor in the same clinic as D-01 (idempotent; test database only)."""
    from cm.core.db import transaction

    with transaction() as conn:
        conn.execute(
            "INSERT INTO cm.persons (role, token, clinic_id, district_id) "
            "SELECT 'doctor', 'D-98', clinic_id, district_id FROM cm.persons WHERE token='D-01' "
            "ON CONFLICT (token) DO NOTHING"
        )
        return conn.execute("SELECT person_id FROM cm.persons WHERE token='D-98'").fetchone()["person_id"]
