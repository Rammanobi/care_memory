"""Fixtures for DB-backed tests: fresh approvals for a seeded patient and the doctor."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from cm.core import clock
from cm.core.db import transaction
from cm.store import approvals_repo


@pytest.fixture()
def actors(pinned_clock: None) -> dict[str, Any]:
    with transaction() as conn:
        pat = conn.execute(
            "SELECT p.patient_id, p.person_id FROM cm.patients p JOIN cm.persons per USING (person_id) "
            "WHERE per.token = 'P-0142'"
        ).fetchone()
        doc = conn.execute("SELECT person_id FROM cm.persons WHERE token = 'D-01'").fetchone()
    return {
        "patient_id": pat["patient_id"],
        "patient_person": pat["person_id"],
        "doctor": doc["person_id"],
    }


@pytest.fixture()
def make_approval(actors: dict[str, Any]) -> Callable[..., UUID]:
    def _make(
        tier: str = "amber",
        body: str = "Please come to the clinic on Friday.",
        audience: str = "patient",
        recipients: bool = True,
    ) -> UUID:
        at = clock.now()
        rid = uuid4()
        who = [
            {"person_id": str(actors["patient_person"]), "token": "P-0142", "channel": "telegram"}
        ]
        payload = {
            "audience": audience,
            "title": "Test draft",
            "channel": "telegram",
            "body": body,
            "recipients": who if recipients else [],
            "subkind": "outreach",
            "data": {},
        }
        with transaction() as conn:
            return approvals_repo.upsert(
                {
                    "approval_id": rid,
                    "patient_id": actors["patient_id"],
                    "thread_id": f"t-{rid}",
                    "interrupt_id": "test",
                    "tier": tier,
                    "kind": "needs_human",
                    "payload": payload,
                    "created_at": at,
                    "due_at": at + timedelta(hours=4),
                    "expires_at": at + timedelta(hours=48),
                },
                conn=conn,
            )

    return _make
