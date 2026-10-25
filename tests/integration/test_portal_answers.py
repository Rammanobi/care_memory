"""GET /portal/answers on caremem_test: patient only, own data only, banned-term clean, as_of respected."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from cm.api.main import create_app
from cm.api.routers.auth import reset_rate_limits
from cm.core import clock
from cm.core.banned_lexicon import find_banned
from cm.core.db import transaction
from cm.jobs import seed_demo_accounts as sda
from tests.integration.test_e2e_api import _as

pytestmark = pytest.mark.db
WEB = {"X-CM-Client": "web"}
SHAPE = {"topic", "question", "answer_text", "numbers", "as_of", "lang"}
PW = {u: f"Pw-{u}-test-only" for u in ("demo.pt0906", "demo.pt0960")}


def _retry(fn: Any) -> Any:
    try:
        return fn()
    except psycopg.errors.DeadlockDetected:  # shared caremem_test
        return fn()


@pytest.fixture(scope="module")
def demo(seeded_db: None) -> Iterator[None]:
    mp = pytest.MonkeyPatch()
    mp.setenv("CM_DATA_CLASS", "mock")
    mp.setenv("DEMO_ACCOUNT_PASSWORDS", json.dumps(PW))

    def setup() -> None:
        with transaction() as conn:
            sda.apply_bundle(conn, sda.build_bundle())

    _retry(setup)
    yield
    mp.undo()


@pytest.fixture()
def at_demo_day(demo: None) -> Iterator[None]:
    reset_rate_limits()
    clock.pin(sda.as_of_instant())
    yield
    clock.unpin()


def _demo_client(user: str) -> TestClient:
    c = TestClient(create_app(), headers=WEB)
    r = c.post("/auth/login", json={"username": user, "password": PW[user]})
    assert r.status_code == 200, r.text
    return c


def _by_topic(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["topic"]: r for r in rows}


def test_shape_and_footer(at_demo_day: None) -> None:
    r = _demo_client("demo.pt0960").get("/portal/answers")
    assert r.status_code == 200
    rows = r.json()
    assert all(set(c) == SHAPE for c in rows)
    cards = _by_topic(rows)
    assert {"taken_week", "missed_week", "streak", "next_visit", "last_refill", "advice"} <= cards.keys()
    assert rows[-1]["topic"] == "advice"
    assert rows[-1]["answer_text"] == "For any question about your medicines, food or symptoms, ask your care team."
    t, m = cards["taken_week"]["numbers"]["taken_7d"], cards["missed_week"]["numbers"]["missed_7d"]
    assert 0 <= t <= 7 and 0 <= m <= 7 and t + m <= 7
    assert f"took {t} of 7 doses" in cards["taken_week"]["answer_text"]
    assert all(c["lang"] == "en" for c in rows)
    for c in rows:
        assert find_banned(c["answer_text"]) == [] and find_banned(c["question"]) == []


def test_numbers_match_the_record_endpoint(at_demo_day: None) -> None:
    c = _demo_client("demo.pt0960")
    cards = _by_topic(c.get("/portal/answers").json())
    days = c.get("/portal/record").json()["days"][-7:]
    assert cards["taken_week"]["numbers"]["taken_7d"] == sum(d["status"] == "taken" for d in days)
    assert cards["missed_week"]["numbers"]["missed_7d"] == sum(d["status"] == "missed" for d in days)
    assert cards["streak"]["numbers"]["streak_days"] == c.get("/portal/today").json()["streak"]


def test_six_day_patient_answers(at_demo_day: None) -> None:
    cards = _by_topic(_demo_client("demo.pt0906").get("/portal/answers").json())
    # six check-ins is enough history; each patient sees only their own numbers
    assert "history" not in cards and "taken_week" in cards


def test_isolation_between_patients(at_demo_day: None) -> None:
    a = _demo_client("demo.pt0906").get("/portal/answers").json()
    b = _demo_client("demo.pt0960").get("/portal/answers").json()
    assert a != b
    # no patient id or token field can leak through the response
    assert "P-09" not in json.dumps(a) + json.dumps(b)


def test_future_events_invisible(at_demo_day: None) -> None:
    c = _demo_client("demo.pt0906")
    before = c.get("/portal/answers").json()
    clock.pin(sda.as_of_instant().replace(year=2026, month=8, day=28))  # long before the history exists
    after = _by_topic(c.get("/portal/answers").json())
    assert "history" in after and "taken_week" not in after
    clock.pin(sda.as_of_instant())
    assert c.get("/portal/answers").json() == before


def test_telugu_from_vault_language(at_demo_day: None) -> None:
    def set_lang(lang: str) -> None:
        with transaction() as conn:
            conn.execute(
                "UPDATE cm.identity_vault SET lang=%s WHERE person_id=(SELECT person_id FROM cm.persons WHERE token='P-0906')",
                (lang,),
            )

    c = _demo_client("demo.pt0906")
    set_lang("te")
    try:
        rows = c.get("/portal/answers").json()
    finally:
        set_lang("en")
    assert all(r["lang"] == "te" and any("ఀ" <= ch <= "౿" for ch in r["answer_text"]) for r in rows)
    assert all(find_banned(r["answer_text"]) == [] for r in rows)


def test_patient_only(pinned_clock: None) -> None:
    reset_rate_limits()
    assert TestClient(create_app(), headers=WEB).get("/portal/answers").status_code == 401
    assert _as("dr.rao").get("/portal/answers").status_code == 403
    assert _as("lakshmi.s01").get("/portal/answers").status_code == 403
    assert _as("ravi.pt0142").get("/portal/answers").status_code == 200


def test_client_cannot_pick_another_patient(at_demo_day: None) -> None:
    c = _demo_client("demo.pt0906")
    base = c.get("/portal/answers").json()
    assert c.get("/portal/answers", params={"patient": "PT-0960", "token": "P-0960"}).json() == base
