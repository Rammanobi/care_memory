"""Backend gaps slice 1: undo dose, documents, medicines, bulk results, stream, district, settings."""

import json
import os
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from cm.api.deps import User
from cm.api.main import create_app
from cm.api.routers.auth import reset_rate_limits
from cm.api.routers.stream import event_iter
from cm.api.suppress import SMALL_CELL_THRESHOLD, find_banned
from cm.core.db import transaction
from cm.store import settings_repo

pytestmark = pytest.mark.db
WEB = {"X-CM-Client": "web"}


def _as(user: str) -> TestClient:
    reset_rate_limits()
    c = TestClient(create_app(), headers=WEB)
    pw = json.loads(os.environ["DEMO_USER_PASSWORDS"])[user]
    assert c.post("/auth/login", json={"username": user, "password": pw}).status_code == 200
    return c


@pytest.fixture()
def patient(pinned_clock: None) -> Iterator[TestClient]:
    with _as("ravi.pt0142") as c:
        yield c


@pytest.fixture()
def doctor(pinned_clock: None) -> Iterator[TestClient]:
    with _as("dr.rao") as c:
        yield c


def _dose_rows() -> int:
    with transaction() as conn:
        return conn.execute(
            "SELECT count(*) AS n FROM cm.events e JOIN cm.patients p USING (patient_id) "
            "JOIN cm.persons per USING (person_id) WHERE per.token='P-0142' AND e.type='DoseCheckin'"
        ).fetchone()["n"]


def test_undo_dose_is_compensating_and_idempotent(patient: TestClient) -> None:
    assert patient.post("/portal/dose", json={"status": "taken"}).json()["today"] == "taken"
    before = _dose_rows()
    first = patient.delete("/portal/dose")
    assert first.status_code == 200 and first.json()["today"] == "none"
    after_one = _dose_rows()
    assert after_one == before + 1  # a new compensating row; nothing removed
    assert patient.delete("/portal/dose").json()["today"] == "none"
    assert _dose_rows() == after_one  # second undo changes nothing
    assert patient.post("/portal/dose", json={"status": "missed"}).json()["today"] == "missed"
    patient.delete("/portal/dose")


def test_documents_and_medicines_are_plain_and_clean(patient: TestClient) -> None:
    docs = patient.get("/portal/documents").json()
    assert len(docs) >= 3 and {d["kind"] for d in docs} >= {"visit_summary", "lab_slip"}
    meds = patient.get("/portal/medicines").json()
    assert [m["label"] for m in meds] == ["Morning tablets", "Evening vitamin"]
    assert find_banned(json.dumps(docs)) == [] and find_banned(json.dumps(meds)) == []


def test_documents_banned_term_withheld(patient: TestClient) -> None:
    with transaction() as conn:
        pat = conn.execute(
            "SELECT p.patient_id FROM cm.patients p JOIN cm.persons per USING (person_id) "
            "WHERE per.token='P-0142'"
        ).fetchone()
        conn.execute(
            "INSERT INTO cm.events (patient_id,type,occurred_at,recorded_at,source,reporter_mode,"
            "payload,idempotency_key) VALUES (%s,'ContextNote',now(),now(),'console','record',%s,%s)",
            (
                pat["patient_id"],
                json.dumps({"kind": "document", "id": "bad", "title": "TB report", "summary": "x"}),
                f"test:baddoc:{uuid.uuid4()}",
            ),
        )
    res = patient.get("/portal/documents")
    assert res.status_code == 200
    assert "TB report" not in [d["title"] for d in res.json()]


def test_role_guard_on_new_portal_routes(doctor: TestClient) -> None:
    for path in ("/portal/documents", "/portal/medicines"):
        assert doctor.get(path).status_code == 403
    assert doctor.delete("/portal/dose").status_code == 403


def test_ui_patient_has_person_id(doctor: TestClient) -> None:
    rows = doctor.get("/patients").json()["items"]
    assert rows and all(UUID(r["person_id"]) for r in rows)
    assert doctor.get(f"/consents/{rows[0]['person_id']}").status_code == 200


def test_bulk_decision_per_item_results(
    doctor: TestClient, make_approval: Callable[..., UUID]
) -> None:
    green, red, amber = make_approval("green"), make_approval("red"), make_approval("amber")
    ghost = uuid.uuid4()
    ids = [str(x) for x in (green, red, amber, ghost)]
    r = doctor.post("/review/bulk-decision", json={"approval_ids": ids})
    assert r.status_code == 200
    by = {UUID(x["approval_id"]): x for x in r.json()}
    assert by[green]["ok"] is True and by[green]["error_code"] is None
    assert (by[red]["ok"], by[red]["error_code"]) == (False, "red_not_bulk")
    assert (by[amber]["ok"], by[amber]["error_code"]) == (False, "amber_not_viewed")
    assert by[ghost]["error_code"] == "not_found" and by[ghost]["message"]
    again = doctor.post("/review/bulk-decision", json={"approval_ids": [str(green)]}).json()
    assert again[0]["ok"] is True or again[0]["error_code"] == "already_decided"


def test_stream_requires_auth() -> None:
    assert TestClient(create_app()).get("/stream").status_code == 401


def _user(role: str) -> User:
    return User(uuid.uuid4(), role, "T", None, None, None, None)


def test_stream_emits_events_and_heartbeat(
    pinned_clock: None, make_approval: Callable[..., UUID]
) -> None:
    it = event_iter(_user("doctor"), {"review"}, heartbeat_s=0.3, tick_s=0.1)
    assert "connected" in next(it)
    got: list[str] = []

    def reader() -> None:
        for frame in it:
            got.append(frame)
            if "event:" in frame:
                return

    t = threading.Thread(target=reader)
    t.start()
    time.sleep(0.8)  # long enough for a heartbeat
    aid = make_approval("green")
    t.join(10)
    assert any(f.startswith(": ping") for f in got)
    ev = next(f for f in got if "event:" in f)
    assert ev.startswith("event: review") and "approval_created" in ev and str(aid) in ev


def test_stream_patient_sees_only_own(
    pinned_clock: None, make_approval: Callable[..., UUID]
) -> None:
    it = event_iter(_user("patient"), set(), heartbeat_s=0.2, tick_s=0.1)
    next(it)
    make_approval("green")  # concerns another person than the random user
    frames = [next(it) for _ in range(3)]
    assert not any("event:" in f for f in frames)


def test_district_suppresses_small_cells(doctor: TestClient) -> None:
    d = doctor.get("/dashboard/district").json()
    assert d["small_cell_threshold"] == SMALL_CELL_THRESHOLD and d["clinics"]
    for c in d["clinics"]:
        for field in ("patients", "quiet", "pending"):
            v = c[field]
            assert v is None or v == 0 or v >= SMALL_CELL_THRESHOLD
            assert (v is None) == (field in c["suppressed"])
    assert doctor.get("/dashboard/district?clinic=nowhere").json()["clinics"] == []


def test_message_list_has_delivery(doctor: TestClient) -> None:
    rows: list[dict[str, Any]] = doctor.get("/messages").json()
    assert all(r["delivery"] in ("queued", "sent", "failed") for r in rows)


def test_admin_settings_put_and_conflict(pinned_clock: None) -> None:
    admin = _as("admin.demo")
    cur = admin.get("/admin/settings").json()
    settings_repo.clear_cache()
    body = {"version": cur["version"], "values": {**cur["values"], "red_escalation_hours": 5}}
    ok = admin.put("/admin/settings", json=body)
    assert ok.status_code == 200, ok.text
    assert ok.json()["values"]["red_escalation_hours"] == 5
    assert ok.json()["version"] == cur["version"] + 1
    stale = admin.put("/admin/settings", json=body)  # the old version again
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
    assert _as("dr.rao").put("/admin/settings", json=body).status_code == 403
    back = {"version": ok.json()["version"], "values": cur["values"]}
    assert admin.put("/admin/settings", json=back).status_code == 200
