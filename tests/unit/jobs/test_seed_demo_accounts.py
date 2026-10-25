"""cm.jobs.seed_demo_accounts against caremem_test: additive, idempotent, spans, no future, clean text, login."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from cm.core import clock
from cm.core.db import transaction
from cm.core.ids import det_id
from cm.jobs import seed_demo_accounts as sda
from tests.unit.content.conftest import load_banned_terms

pytestmark = pytest.mark.db
PASSWORDS = {u: f"Pw-{u}-test-only" for u in ("demo.pt0906", "demo.pt0960", "demo.pt0903", "demo.pt0930", "demo.sup0930")}


@pytest.fixture()
def demo(seeded_db, monkeypatch):  # noqa: ANN001
    monkeypatch.setenv("CM_DATA_CLASS", "mock")
    monkeypatch.setenv("DEMO_ACCOUNT_PASSWORDS", json.dumps(PASSWORDS))
    with transaction() as conn:
        first = sda.apply_bundle(conn, sda.build_bundle())
    return first


def _count(sql: str, *args) -> int:  # noqa: ANN002
    with transaction() as conn:
        return conn.execute(sql, args).fetchone()["n"]


def test_bundle_is_deterministic() -> None:
    assert json.dumps(sda.build_bundle(), sort_keys=True) == json.dumps(sda.build_bundle(), sort_keys=True)


def test_idempotent_and_additive(demo) -> None:  # noqa: ANN001
    n_events = _count("SELECT count(*) AS n FROM cm.events e JOIN cm.patients p USING (patient_id) WHERE p.nikshay_id IN ('NK-0906','NK-0960')")
    n_pt = _count("SELECT count(*) AS n FROM cm.patients WHERE nikshay_id IN ('NK-0906','NK-0960')")
    n_cons = _count("SELECT count(*) AS n FROM cm.consents c JOIN cm.persons p USING (person_id) WHERE p.token IN ('P-0906','P-0960')")
    with transaction() as conn:
        again = sda.apply_bundle(conn, sda.build_bundle())
    assert again["events_new"] == 0 and again["users_new"] == 0
    assert _count("SELECT count(*) AS n FROM cm.events e JOIN cm.patients p USING (patient_id) WHERE p.nikshay_id IN ('NK-0906','NK-0960')") == n_events
    assert _count("SELECT count(*) AS n FROM cm.patients WHERE nikshay_id IN ('NK-0906','NK-0960')") == n_pt
    assert _count("SELECT count(*) AS n FROM cm.consents c JOIN cm.persons p USING (person_id) WHERE p.token IN ('P-0906','P-0960')") == n_cons


@pytest.mark.parametrize("code,days", [("PT-0906", 6), ("PT-0960", 60)])
def test_spans_and_no_future(demo, code: str, days: int) -> None:  # noqa: ANN001
    as_of, end = sda.as_of_instant(), sda.today_ist()
    pid = det_id("patient", code)
    with transaction() as conn:
        rows = conn.execute(
            "SELECT occurred_at, recorded_at, payload FROM cm.events WHERE patient_id=%s AND type='DoseCheckin'",
            (pid,)).fetchall()
        everything = conn.execute("SELECT occurred_at, recorded_at FROM cm.events WHERE patient_id=%s", (pid,)).fetchall()
        start = conn.execute("SELECT treatment_start FROM cm.patients WHERE patient_id=%s", (pid,)).fetchone()
    assert start["treatment_start"] == end - timedelta(days=days)
    dates = {clock.ist_date(r["occurred_at"]) for r in rows}
    assert dates and max(dates) <= end - timedelta(days=1) and min(dates) >= end - timedelta(days=days)
    assert len(rows) == len(dates) <= days
    assert len(rows) >= days * 0.7  # reporting noise drops at most a few days
    assert all(r["occurred_at"] <= as_of and r["recorded_at"] <= as_of for r in everything)


def test_patient_facing_text_is_clean(demo) -> None:  # noqa: ANN001
    banned = load_banned_terms()
    for e in sda.build_bundle()["events"]:
        text = str(e["payload"].get("text_tokenised", "")) + str(e["payload"].get("reason", ""))
        assert not banned.scan_text(text), text


def _legacy_extras() -> None:
    """Create the retired extras the way the earlier 3/30/60 run did (users only; enough to test retiring)."""
    with transaction() as conn:
        for tok, user in (("P-0903", "demo.pt0903"), ("P-0930", "demo.pt0930"), ("S-93", "demo.sup0930")):
            pid = det_id("person", tok)
            conn.execute("INSERT INTO cm.persons (person_id, role, token) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                         (pid, "supporter" if tok == "S-93" else "patient", tok))
            conn.execute("INSERT INTO cm.auth_credentials (person_id, username, password_hash) VALUES (%s,%s,%s) "
                         "ON CONFLICT DO NOTHING", (pid, user, sda.hash_password(PASSWORDS[user])))


def _client():  # noqa: ANN202
    from fastapi.testclient import TestClient

    from cm.api.main import create_app
    from cm.api.routers.auth import reset_rate_limits

    reset_rate_limits()
    return TestClient(create_app())


def _login(c, user: str):  # noqa: ANN001, ANN202
    return c.post("/auth/login", json={"username": user, "password": PASSWORDS[user]})


def test_two_default_accounts() -> None:
    assert [a["code"] for a in sda.ACCOUNTS] == ["PT-0906", "PT-0960"]
    assert [a["days"] for a in sda.ACCOUNTS] == [6, 60]
    assert all(a["supporter"] is None for a in sda.ACCOUNTS)


def test_login_through_api(demo) -> None:  # noqa: ANN001
    c = _client()
    for user in ("demo.pt0906", "demo.pt0960"):
        r = _login(c, user)
        assert r.status_code == 200 and r.json()["role"] == "patient"
    bad = c.post("/auth/login", json={"username": "demo.pt0906", "password": "wrong"})
    assert bad.status_code == 401


def test_retire_disables_logins_and_keeps_data(demo) -> None:  # noqa: ANN001
    from cm.store import auth_repo

    _legacy_extras()
    c = _client()
    assert all(_login(c, u).status_code == 200 for u in sda.RETIRED_USERS)
    with transaction() as conn:
        assert auth_repo.disable_login(sda.RETIRED_USERS, conn=conn) == 3
    with transaction() as conn:
        assert auth_repo.disable_login(sda.RETIRED_USERS, conn=conn) == 0  # idempotent
    assert all(_login(c, u).status_code == 401 for u in sda.RETIRED_USERS)
    assert all(_login(c, u).status_code == 200 for u in ("demo.pt0906", "demo.pt0960"))
    assert _count("SELECT count(*) AS n FROM cm.auth_credentials WHERE username = ANY(%s)", sda.RETIRED_USERS) == 3
    # no supported way to hide a patient from the doctor list: the schema status values do not cover it
    from cm.api import readmodels

    assert "<> 'erased'" in readmodels._PATIENTS_SQL


def test_export_import_roundtrip(demo) -> None:  # noqa: ANN001
    with transaction() as conn:
        b = sda.export_bundle(conn)
    assert len(b["events"]) == len(sda.build_bundle()["events"])
    with transaction() as conn:
        assert sda.apply_bundle(conn, b)["events_new"] == 0


def test_refuses_without_mock(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("CM_DATA_CLASS", "real")
    monkeypatch.setattr(sda, "load_dotenv", lambda: None)
    with pytest.raises(sda.DemoSeedError):
        sda._guard()
