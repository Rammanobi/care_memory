"""Document upload core against caremem_test: intake rules and the /portal/documents routes."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest

from cm.core.db import transaction
from cm.store import uploads_repo
from cm.uploads import intake
from cm.uploads.intake import accept_upload
from tests.integration.test_e2e_api import _as

pytestmark = pytest.mark.db

PT, OTHER, NOCONSENT = "P-0142", "P-0087", "P-7001"


def png(n: int = 0) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + n.to_bytes(4, "big") + b"\x00" * 24


def up(token: str = PT, data: bytes | None = None, **kw):  # noqa: ANN003, ANN201
    return accept_upload(
        patient_token=token,
        source=kw.pop("source", "portal"),
        filename=kw.pop("filename", "slip.png"),
        mime="image/png",
        data=data if data is not None else png(),
        **kw,
    )


def _rows(token: str) -> list[dict]:
    return uploads_repo.list_for_patient(token)


@pytest.fixture(autouse=True)
def clean(pinned_clock: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))

    def wipe() -> None:
        with transaction() as c:
            c.execute("DELETE FROM cm.documents WHERE extra ? 'upload_state'")
            c.execute(
                "DELETE FROM cm.patients WHERE person_id IN (SELECT person_id FROM cm.persons WHERE token=%s)",
                (NOCONSENT,),
            )
            c.execute("DELETE FROM cm.persons WHERE token=%s", (NOCONSENT,))

    wipe()
    yield
    wipe()


@pytest.fixture()
def no_consent_patient() -> str:
    with transaction() as c:
        clinic = c.execute("SELECT clinic_id FROM cm.persons WHERE token=%s", (PT,)).fetchone()[
            "clinic_id"
        ]
        pid = c.execute(
            "INSERT INTO cm.persons (role, token, clinic_id) VALUES ('patient',%s,%s) RETURNING person_id",
            (NOCONSENT, clinic),
        ).fetchone()["person_id"]
        c.execute(
            "INSERT INTO cm.patients (person_id, clinic_id, treatment_start, regimen) VALUES (%s,%s,'2026-01-01','x')",
            (pid, clinic),
        )
    return NOCONSENT


def test_happy_path_stores_file_and_row(tmp_path: Path) -> None:
    r = up(data=png(1))
    assert (r.status, r.duplicate, r.reason) == ("received", False, None) and r.document_id
    row = _rows(PT)[0]
    assert (
        str(row["document_id"]) == r.document_id and row["consent_id"] and row["status"] == "active"
    )
    assert row["extra"]["upload_state"] == "received" and row["extra"]["filename"] == "slip.png"
    assert (tmp_path / "uploads" / PT / row["extra"]["sha256"]).read_bytes() == png(1)


def test_unknown_patient_and_no_consent(no_consent_patient: str) -> None:
    assert up("P-4242").reason == "unknown_patient"
    assert up(no_consent_patient).reason == "no_consent"
    assert _rows(no_consent_patient) == []


def test_duplicate_bytes_per_patient_only() -> None:
    a = up(data=png(2))
    b = up(data=png(2), filename="again.png")
    assert b.duplicate and b.document_id == a.document_id and b.reason == "duplicate"
    assert len(_rows(PT)) == 1
    other = up(OTHER, data=png(2))  # same bytes, other patient: its own document
    assert not other.duplicate and other.document_id != a.document_id


def test_rate_limit_five_per_hour_and_duplicates_do_not_count() -> None:
    for i in range(5):
        assert up(data=png(10 + i)).reason is None
    up(data=png(10))  # a duplicate is not a new upload
    assert up(data=png(99)).reason == "rate_limited"
    assert up(OTHER, data=png(99)).reason is None  # per patient


def test_origin_key_idempotent_even_with_different_bytes() -> None:
    o = {"telegram_file_unique_id": "AgADxyz"}
    a = up(source="telegram", data=png(20), origin=o)
    b = up(source="telegram", data=png(21), origin=o)
    assert b.duplicate and b.document_id == a.document_id
    g = {"gmail_message_id": "m1", "gmail_attachment_id": "a1"}
    c = up(source="gmail", data=png(22), origin=g)
    assert up(source="gmail", data=png(23), origin=g).document_id == c.document_id
    assert (
        up(source="gmail", data=png(24), origin={**g, "gmail_attachment_id": "a2"}).duplicate
        is False
    )


def test_rejections_never_raise_and_write_nothing(tmp_path: Path) -> None:
    assert up(data=b"MZ\x90\x00" + b"\x00" * 64).reason == "bad_type"
    assert up(data=b"").reason == "bad_type"
    assert up(data=png() + b"\x00" * (11 * 1024 * 1024)).reason == "too_large"
    assert _rows(PT) == [] and not (tmp_path / "uploads").exists()


def test_storage_error_is_a_reason_code() -> None:
    class Broken:
        def put(self, key: str, data: bytes) -> str:
            raise OSError("disk full")

    r = accept_upload(
        patient_token=PT,
        source="portal",
        filename="a.png",
        mime="",
        data=png(30),
        storage=Broken(),  # type: ignore[arg-type]
    )
    assert r.reason == "storage_error" and r.document_id is None and _rows(PT) == []


def test_consent_check_per_channel_and_lifecycle_in_extra() -> None:
    r = up(source="telegram", data=png(40), origin={"telegram_file_unique_id": "zz"})
    assert r.reason is None
    doc = uploads_repo.get(UUID(r.document_id))
    assert doc["source"] == "telegram" and doc["status"] == "active"
    assert uploads_repo.set_state(doc["document_id"], "pending_review", {"x": 1})
    assert uploads_repo.get(doc["document_id"])["extra"]["upload_state"] == "pending_review"
    assert intake.RATE_LIMIT == 5


# ---- portal routes ---------------------------------------------------------------------------
def _post(c, data: bytes, name: str = "slip.png"):  # noqa: ANN001, ANN202
    return c.post("/portal/documents", files={"file": (name, data, "image/png")})


def test_portal_requires_patient_role_and_login() -> None:
    from fastapi.testclient import TestClient

    from cm.api.main import create_app

    assert (
        TestClient(create_app())
        .post("/portal/documents", files={"file": ("a.png", png(), "image/png")})
        .status_code
        == 401
    )
    assert _post(_as("dr.rao"), png()).status_code == 403


def test_portal_upload_ignores_client_supplied_patient_and_lists_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(
        "cm.core.tasks.enqueue", lambda q, name, payload, **k: queued.append((q, name, payload))
    )
    c = _as("ravi.pt0142")
    r = c.post(
        "/portal/documents",
        data={"patient_token": OTHER, "patient_id": OTHER},
        files={"file": ("../../evil name.png", png(50), "image/png")},
    )
    assert r.status_code == 201, r.text
    assert r.json() == {
        "document_id": r.json()["document_id"],
        "status": "received",
        "duplicate": False,
    }
    assert len(_rows(PT)) == 1 and _rows(OTHER) == []
    did = r.json()["document_id"]
    assert queued == [("agent-runs", f"docx-{did}", {"kind": "document_extract", "document_id": did})]
    assert _rows(PT)[0]["extra"]["filename"] == "evil name.png"
    again = _post(c, png(50))
    assert len(queued) == 1  # a duplicate upload does not enqueue again
    assert (
        again.json()["duplicate"] is True and again.json()["document_id"] == r.json()["document_id"]
    )

    docs = {d["id"]: d for d in c.get("/portal/documents").json()}
    mine = docs[r.json()["document_id"]]
    assert (
        mine["status"] == "received" and mine["title"] == "evil name.png" and mine["summary"] == ""
    )
    assert all(d["status"] for d in docs.values())  # seeded notes default to "added to your record"


def test_get_status_mapping_and_isolation() -> None:
    c = _as("ravi.pt0142")
    states = ["received", "extracting", "pending_review", "accepted", "failed"]
    ids = [up(data=png(60 + i)).document_id for i in range(len(states))]
    for doc_id, st in zip(ids, states, strict=True):
        uploads_repo.set_state(UUID(doc_id), st, {"extracted_text": "secret contents"})
    other = up(OTHER, data=png(70)).document_id
    body = c.get("/portal/documents")
    by = {d["id"]: d["status"] for d in body.json()}
    assert [by[i] for i in ids] == [
        "received",
        "received",
        "with your care team",
        "added to your record",
        "could not be used",
    ]
    assert other not in by and "secret contents" not in body.text


def test_portal_errors_are_patient_safe_and_size_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _as("ravi.pt0142")
    bad = _post(c, b"MZ\x90\x00" + b"\x00" * 64, "a.png")
    assert bad.status_code == 415 and bad.json()["code"] == "bad_type"
    monkeypatch.setenv("UPLOAD_MAX_MB", "1")
    big = _post(c, png() + b"\x00" * (1024 * 1024 + 10))
    assert big.status_code == 413 and big.json()["code"] == "too_large"
    assert _rows(PT) == []
    monkeypatch.setenv("UPLOAD_MAX_MB", "10")
    for i in range(5):
        assert _post(c, png(80 + i)).status_code == 201
    limited = _post(c, png(99))
    assert limited.status_code == 429
    from cm.api.suppress import find_banned

    for resp in (bad, big, limited):
        assert find_banned(resp.text) == []


def test_concurrent_uploads_respect_rate_limit_exactly() -> None:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: up(data=png(200 + i)), range(8)))
    assert sorted(r.reason or "ok" for r in results) == ["ok"] * 5 + ["rate_limited"] * 3
    assert len(_rows(PT)) == 5


def test_default_storage_root_is_repo_relative(monkeypatch: pytest.MonkeyPatch) -> None:
    from cm.core.config import REPO_ROOT
    from cm.uploads.storage import LocalStorage

    monkeypatch.delenv("UPLOAD_DIR", raising=False)
    monkeypatch.chdir("/")
    assert LocalStorage().root == (Path(REPO_ROOT) / "data" / "uploads").resolve()
