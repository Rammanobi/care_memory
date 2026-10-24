"""End to end through the HTTP API: doctor approves, outbox row exists, patient inbox shows the message."""

import json
import os
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from cm.api.main import create_app
from cm.api.routers.auth import reset_rate_limits
from cm.core.db import transaction

pytestmark = pytest.mark.db
WEB = {"X-CM-Client": "web"}


@pytest.fixture()
def app_client(pinned_clock: None) -> Iterator[TestClient]:
    reset_rate_limits()
    with TestClient(create_app(), headers=WEB) as c:
        yield c


def _login(client: TestClient, user: str) -> TestClient:
    pw = json.loads(os.environ["DEMO_USER_PASSWORDS"])[user]
    r = client.post("/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    assert "cm_session" in client.cookies
    return client


def _as(user: str) -> TestClient:
    return _login(TestClient(create_app(), headers=WEB), user)


def test_login_errors_are_problem_bodies(app_client: TestClient) -> None:
    r = app_client.post("/auth/login", json={"username": "dr.rao", "password": "nope"})
    assert r.status_code == 401
    body = r.json()
    assert body["title"] and body["status"] == 401 and body["code"] == "bad_credentials"
    assert app_client.get("/auth/me").status_code == 401


def test_roles_are_enforced(app_client: TestClient) -> None:
    patient = _as("ravi.pt0142")
    assert patient.get("/review/queue").status_code == 403
    assert patient.get("/patients").json()["code"] == "forbidden_scope"
    doctor = _as("dr.rao")
    assert doctor.get("/portal/me").status_code == 403
    assert doctor.post("/auth/logout").status_code == 204


def test_doctor_approves_and_patient_sees_it(app_client: TestClient) -> None:
    doctor = _as("dr.rao")
    assert doctor.get("/auth/me").json()["role"] == "doctor"
    queue = doctor.get("/review/queue", params={"status": "pending"}).json()
    assert queue["counts"]["red"] >= 1 and queue["items"]
    item = next(
        i
        for i in queue["items"]
        if i["patient_token"] == "P-0142" and i["title"].startswith("Confirm visit")
    )
    detail = doctor.get(f"/review/{item['approval_id']}").json()
    assert detail["proposal"]["recipients"] and detail["evidence"]

    out = doctor.post(f"/review/{item['approval_id']}/decision", json={"action": "approve"})
    assert out.status_code == 200, out.text
    result: dict[str, Any] = out.json()
    assert result["status"] == "approved" and len(result["outbox_ids"]) == 1
    again = doctor.post(
        f"/review/{item['approval_id']}/decision", json={"action": "approve"}
    ).json()
    assert again["decision_id"] == result["decision_id"]  # double click
    conflict = doctor.post(
        f"/review/{item['approval_id']}/decision", json={"action": "reject", "reason": "x"}
    )
    assert conflict.status_code == 409 and conflict.json()["code"] == "already_decided"

    with transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM cm.outbox WHERE approval_id=%s", (item["approval_id"],)
        ).fetchall()
    assert len(rows) == 1 and rows[0]["decision_id"] and rows[0]["status"] == "pending"

    inbox = _as("ravi.pt0142").get("/portal/inbox").json()
    assert any(m["id"] == result["outbox_ids"][0] and "Wednesday" in m["text"] for m in inbox)


def test_banned_term_is_refused_at_decision_and_filtered_from_patient(
    app_client: TestClient,
) -> None:
    doctor = _as("dr.rao")
    item = next(
        i for i in doctor.get("/review/queue").json()["items"] if i["patient_token"] == "P-0087"
    )
    bad = doctor.post(
        f"/review/{item['approval_id']}/decision",
        json={"action": "edit", "edited": {"body": "Your TB test is ready."}},
    )
    assert bad.status_code == 422 and bad.json()["code"] == "banned_term"
    text = json.dumps(_as("ravi.pt0142").get("/portal/inbox").json()).lower()
    assert "tuberculosis" not in text and " tb " not in text


def test_patient_request_flow(app_client: TestClient) -> None:
    patient = _as("ravi.pt0142")
    made = patient.post("/portal/reminder-request", json={"time": "7:00 pm"})
    assert made.status_code == 201 and made.json()["status"] == "waiting"
    assert patient.get("/portal/me").json()["pending_reminder"] == "7:00 pm"
    doctor = _as("dr.rao")
    waiting = [
        r
        for r in doctor.get("/requests", params={"status": "waiting"}).json()
        if r["id"] == made.json()["id"]
    ]
    assert waiting and "7:00 pm" in waiting[0]["draft"]
    done = doctor.post(f"/requests/{waiting[0]['id']}/decision", json={"action": "approve"})
    assert done.status_code == 200
    me = patient.get("/portal/me").json()
    assert me["reminder"] == "7:00 pm" and me["pending_reminder"] is None


def test_patient_dose_and_supporter_view(app_client: TestClient) -> None:
    patient = _as("ravi.pt0142")
    before = patient.get("/portal/today").json()
    assert len(before["history"]) == 60
    after = patient.post("/portal/dose", json={"status": "taken"}).json()
    assert after["today"] == "taken" and after["marked_by"] == "self"
    assert (
        patient.post("/portal/dose", json={"status": "taken"}).json()["today"] == "taken"
    )  # idempotent
    view = _as("lakshmi.s01").get("/portal/supporter/checkin").json()
    assert view["allowed"] and view["today"] == "taken" and view["week"].endswith("o")


def test_other_endpoints_answer(app_client: TestClient) -> None:
    doctor = _as("dr.rao")
    assert doctor.get("/patients").json()["total"] == 6
    assert doctor.get("/dashboard/tiles").json()["all"] == 6
    ans = doctor.post("/query", json={"question": "Why is PT-0142 flagged?"}).json()
    assert ans["numbers_verified"] and ans["tool_calls_used"]
    assert doctor.get("/admin/usage").status_code == 200
    assert doctor.get("/healthz").json() == {"status": "ok"}
