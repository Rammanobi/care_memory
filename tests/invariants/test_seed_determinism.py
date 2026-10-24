"""Seed determinism: seeding caremem_test twice with the same seed gives identical data.

Random surrogate keys (gen_random_uuid) are masked, so the check is on content and shape: every row,
every reference pattern, every payload. Wall-clock metadata (created_at/updated_at, the consents
ledger's recorded_at default) and salted password hashes are the only columns allowed to differ.
"""

from __future__ import annotations

import hashlib
import re

import pytest

pytestmark = [pytest.mark.db, pytest.mark.slow]
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
WALL_CLOCK = {"created_at", "updated_at"}
ALLOWED = {("consents", "recorded_at"), ("auth_credentials", "password_hash")}


def _fingerprint() -> dict[tuple[str, str], str]:
    from cm.core.db import connect_direct

    out: dict[tuple[str, str], str] = {}
    with connect_direct() as c:
        assert c.execute("SELECT current_database() AS d").fetchone()["d"] != "caremem"
        tabs = [r["table_name"] for r in c.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='cm' AND table_type='BASE TABLE'"
        )]  # fmt: skip
        for t in tabs:
            cols = [r["column_name"] for r in c.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='cm' AND table_name=%s", (t,)
            )]  # fmt: skip
            for col in cols:
                if col in WALL_CLOCK or (t, col) in ALLOWED:
                    continue
                vals = sorted(
                    UUID_RE.sub("<uuid>", str(r["v"]))
                    for r in c.execute(f'SELECT "{col}"::text AS v FROM cm."{t}"')  # noqa: S608 (catalog names)
                )
                out[(t, col)] = hashlib.sha256("\n".join(vals).encode()).hexdigest()
    return out


def test_same_seed_gives_identical_data(seeded_db: None) -> None:
    from cm.jobs.seed import run_seed

    run_seed(small=True, reset=True)
    first = _fingerprint()
    run_seed(small=True, reset=True)
    second = _fingerprint()
    assert first.keys() == second.keys()
    diff = sorted(k for k in first if first[k] != second[k])
    assert diff == [], f"seed is not deterministic in: {diff}"


def test_reseed_without_reset_is_idempotent(seeded_db: None) -> None:
    from cm.core.db import connect_direct
    from cm.jobs.seed import run_seed

    def counts() -> dict[str, int]:
        with connect_direct() as c:
            return {t: c.execute(f"SELECT count(*) AS n FROM cm.{t}").fetchone()["n"]  # noqa: S608
                    for t in ("persons", "patients", "events", "consents", "approvals", "outbox", "templates")}  # fmt: skip

    run_seed(small=True, reset=True)
    before = counts()
    run_seed(small=True, reset=False)
    assert counts() == before
