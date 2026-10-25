"""document_review approvals on the doctor Requests page: shape, queue exclusion, counts, roles, portal safety."""

import importlib
import json
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from cm.core import clock
from cm.core.db import transaction
from cm.store import approvals_repo
from tests.integration.test_e2e_api import _as

pytestmark = pytest.mark.db
SECRET_EXCERPT = "ZZEXCERPTMARKER lab slip text"
SECRET_FIELD = "ZZFIELDMARKER-negative"
PORTAL_PATHS = [
    "/portal/me",
    "/portal/today",
    "/portal/documents",
    "/portal/record",
    "/portal/inbox",
    "/portal/requests",
]


def _doc(doc_id: UUID) -> dict[str, Any]:
    return {
        "id": str(doc_id),
        "filename": "lab_slip.pdf",
        "mime": "application/pdf",
        "size": 182344,
        "pages": 1,
        "status": "pending_review",
        "extraction": {
            "doc_type": "lab_report",
            "method": "pypdf",
            "fields": [{"name": "lab_values[0].value", "value": SECRET_FIELD, "confidence": 0.82}],
            "text_excerpt": SECRET_EXCERPT,
            "low_confidence": ["dates[0]"],
            "error": None,
        },
    }


@pytest.fixture()
def make_doc(actors: dict[str, Any]) -> Iterator[Callable[..., UUID]]:
    made: list[UUID] = []

    def _make(*, tier: str = "amber", priority: str = "routine", age_min: int = 0) -> UUID:
        at = clock.now() - timedelta(minutes=age_min)
        did = uuid4()
        payload = {
            "audience": "doctor",
            "title": "Document to review: lab_report",
            "channel": "console",
            "recipients": [],
            "body": "",
            "subkind": "document_review",
            "data": {
                "kind": "document",
                "text": "Document received via telegram",
                "refs": [],
                "source": "telegram",
                "priority": priority,
                "origin": {"channel": "telegram"},
                "document": _doc(did),
            },
        }
        aid = approvals_repo.upsert(
            {
                "patient_id": actors["patient_id"],
                "thread_id": f"upload-{did}",
                "interrupt_id": "document_review",
                "graph_kind": "deep",
                "tier": tier,
                "kind": "needs_human",
                "payload": payload,
                "created_at": at,
                "due_at": at + timedelta(hours=12),
                "expires_at": at + timedelta(days=7),
            }
        )
        made.append(aid)
        return aid

    yield _make
    with transaction() as conn:  # undecided rows only (decisions are append-only)
        conn.execute(
            "DELETE FROM cm.approvals a WHERE approval_id = ANY(%s) AND NOT EXISTS "
            "(SELECT 1 FROM cm.review_decisions d WHERE d.approval_id=a.approval_id)",
            (made,),
        )


def test_requests_list_includes_documents(make_doc: Callable[..., UUID]) -> None:
    aid = make_doc()
    doctor = _as("dr.rao")
    rows = doctor.get("/requests").json()
    row = next(r for r in rows if r["id"] == str(aid))
    assert row["kind"] == "document" and row["tier"] == "amber" and row["status"] == "waiting"
    assert row["priority"] == "routine" and row["source"] == "telegram"
    doc = row["document"]
    assert doc["filename"] == "lab_slip.pdf" and doc["status"] == "pending_review"
    assert doc["extraction"]["doc_type"] == "lab_report"
    assert doc["extraction"]["fields"][0] == {
        "name": "lab_values[0].value",
        "value": SECRET_FIELD,
        "confidence": 0.82,
    }
    assert doc["extraction"]["text_excerpt"] == SECRET_EXCERPT
    one = doctor.get(f"/requests/{aid}")
    assert one.status_code == 200 and one.json()["document"]["id"] == doc["id"]
    detail = doctor.get("/patients/P-0142").json()
    assert str(aid) in [r["id"] for r in detail["requests"]]
    assert str(aid) not in [i["approval_id"] for i in detail["pending_reviews"]]


def test_sorted_urgent_first_then_oldest(make_doc: Callable[..., UUID]) -> None:
    older = make_doc(age_min=50)
    newer = make_doc(age_min=5)
    urgent = make_doc(tier="red", priority="urgent", age_min=1)
    ids = [r["id"] for r in _as("dr.rao").get("/requests").json()]
    mine = [i for i in ids if i in {str(older), str(newer), str(urgent)}]
    assert mine == [str(urgent), str(older), str(newer)]


def test_queue_hides_documents_but_counts_include_them(make_doc: Callable[..., UUID]) -> None:
    doctor = _as("dr.rao")
    before_q = doctor.get("/review/queue").json()
    before_t = doctor.get("/dashboard/tiles").json()
    aid = make_doc()
    after_q = doctor.get("/review/queue").json()
    assert str(aid) not in [i["approval_id"] for i in after_q["items"]]
    assert after_q["counts"] == before_q["counts"]
    after_t = doctor.get("/dashboard/tiles").json()
    assert after_t["pending_requests"] == before_t["pending_requests"] + 1
    assert after_t["pending_approvals"] == before_t["pending_approvals"]
    waiting = doctor.get("/requests", params={"status": "waiting"}).json()
    assert str(aid) in [r["id"] for r in waiting]


def test_requests_are_doctor_only(make_doc: Callable[..., UUID]) -> None:
    aid = make_doc()
    for user in ("ravi.pt0142", "lakshmi.s01"):
        c = _as(user)
        assert c.get("/requests").status_code == 403
        assert c.get(f"/requests/{aid}").status_code == 403
        assert c.post(f"/requests/{aid}/decision", json={"action": "approve"}).status_code == 403


def test_portal_never_leaks_document_review(make_doc: Callable[..., UUID]) -> None:
    aid = make_doc()
    cases = [("ravi.pt0142", PORTAL_PATHS), ("lakshmi.s01", ["/portal/supporter/checkin"])]
    for user, paths in cases:
        c = _as(user)
        for path in paths:
            r = c.get(path)
            assert r.status_code == 200, (path, r.text)
            text = json.dumps(r.json())
            for needle in (SECRET_EXCERPT, SECRET_FIELD, "lab_slip.pdf", "document_review", str(aid)):
                assert needle not in text, (path, needle)


def _stub_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        mod = importlib.import_module("cm.uploads.review")
    except ImportError:
        return
    monkeypatch.setattr(mod, "on_approved", lambda a: None, raising=False)
    monkeypatch.setattr(mod, "on_rejected", lambda a: None, raising=False)


def test_decision_approve_and_reject(
    make_doc: Callable[..., UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_hooks(monkeypatch)
    doctor = _as("dr.rao")
    a, b = make_doc(), make_doc(tier="green")
    ok = doctor.post(f"/requests/{a}/decision", json={"action": "approve"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "approved" and ok.json()["outbox_ids"] == []
    row = next(r for r in doctor.get("/requests").json() if r["id"] == str(a))
    assert row["status"] == "approved" and row["document"]["id"]
    no_reason = doctor.post(f"/requests/{make_doc()}/decision", json={"action": "reject"})
    assert no_reason.status_code == 422 and no_reason.json()["code"] == "reason_required"
    rej = doctor.post(f"/requests/{b}/decision", json={"action": "reject", "reason": "unreadable"})
    assert rej.status_code == 200, rej.text
    assert rej.json()["status"] == "rejected"
    after = next(r for r in doctor.get("/requests").json() if r["id"] == str(b))
    assert after["status"] == "declined"
