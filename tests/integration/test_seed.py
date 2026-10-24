"""The seed is deterministic and idempotent."""

import pytest

from cm.core.db import transaction
from cm.jobs.seed import run_seed

pytestmark = pytest.mark.db
TABLES = [
    "persons",
    "patients",
    "events",
    "approvals",
    "review_decisions",
    "outbox",
    "audit_log",
    "consents",
    "templates",
    "settings",
    "task_runs",
    "auth_credentials",
    "support_assignments",
]


def _counts() -> dict[str, int]:
    with transaction() as conn:
        return {
            t: conn.execute(f"SELECT count(*) AS n FROM cm.{t}").fetchone()["n"]  # noqa: S608
            for t in TABLES
        }


def test_seed_twice_creates_no_duplicates(seeded_db: None) -> None:
    before = _counts()
    run_seed(small=True)
    assert _counts() == before


def test_seed_content_matches_the_ui(seeded_db: None) -> None:
    with transaction() as conn:
        tokens = {
            r["token"] for r in conn.execute("SELECT token FROM cm.persons WHERE role='patient'")
        }
        assert {"P-0142", "P-0087", "P-0213", "P-0176", "P-0900", "P-0901"} <= tokens
        phone = conn.execute("SELECT enc_phone FROM cm.identity_vault LIMIT 1").fetchone()[
            "enc_phone"
        ]
        assert bytes(phone).decode().startswith("9000000")
        pending = conn.execute(
            "SELECT count(*) AS n FROM cm.approvals WHERE status='pending'"
        ).fetchone()["n"]
        assert pending > 0
