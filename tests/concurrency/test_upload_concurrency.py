# ruff: noqa: F811  (the pts fixture is imported from tests/integration/test_upload_edge.py)
"""Races on the document upload pipeline (caremem_test only; throwaway patients P-7301/P-7302 from
tests/integration/test_upload_edge.py). Every racer starts on a barrier; assertions are on the final rows."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from uuid import UUID

import pytest

from cm.contracts.review import ReviewDecisionIn
from cm.core.db import transaction
from cm.rag.embed import FakeEmbedder
from cm.review.decide import DecisionError, decide
from cm.store import uploads_repo
from cm.uploads import extract as ex
from cm.uploads import intake
from cm.uploads import review as rv
from tests.concurrency.conftest import race
from tests.integration.test_upload_edge import (  # noqa: F401  (pytest fixture)
    A,
    B,
    _chunks_of,
    _doc_events,
    _doctor,
    _txt_doc,
    png,
    pts,
    up,
)

pytestmark = pytest.mark.db


def _files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def test_identical_concurrent_uploads_make_one_document(pts: dict, tmp_path: Path) -> None:
    out = race([lambda: up(A, png(501)) for _ in range(6)])
    assert not [o for o in out if isinstance(o, BaseException)], out
    ids = {o.document_id for o in out}
    assert len(ids) == 1 and None not in ids
    assert Counter(o.duplicate for o in out) == Counter({True: 5, False: 1})
    assert len(uploads_repo.list_for_patient(A)) == 1
    assert len(_files(tmp_path / "uploads")) == 1


def test_concurrent_uploads_over_the_rate_limit_accept_exactly_five(pts: dict) -> None:
    out = race([lambda i=i: up(A, png(600 + i)) for i in range(9)])
    assert not [o for o in out if isinstance(o, BaseException)], out
    reasons = Counter(o.reason for o in out)
    assert reasons == Counter({None: intake.RATE_LIMIT, "rate_limited": 9 - intake.RATE_LIMIT}), (
        reasons
    )
    assert len(uploads_repo.list_for_patient(A)) == intake.RATE_LIMIT


def test_concurrent_rate_limit_is_per_patient(pts: dict) -> None:
    fns = [lambda i=i: up(A, png(700 + i)) for i in range(6)] + [
        lambda i=i: up(B, png(700 + i)) for i in range(6)
    ]
    out = race(fns)
    a = Counter(o.reason for o in out[:6])
    b = Counter(o.reason for o in out[6:])
    assert a == b == Counter({None: 5, "rate_limited": 1})


def test_same_telegram_file_raced_with_different_bytes_stores_once(pts: dict) -> None:
    origin = {"telegram_file_unique_id": "AgADrace"}
    out = race(
        [lambda i=i: up(A, png(800 + i), source="telegram", origin=origin) for i in range(5)]
    )
    assert not [o for o in out if isinstance(o, BaseException)], out
    assert len({o.document_id for o in out}) == 1 and len(uploads_repo.list_for_patient(A)) == 1


def test_concurrent_extract_task_reruns_make_one_review_item(
    pts: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    did = _txt_doc(A, "Lab report smear negative 2026-10-12 race")
    out = race([lambda: rv.run_document_extract(did) for _ in range(4)])
    assert not [o for o in out if isinstance(o, BaseException)], out
    with transaction() as c:
        n = c.execute(
            "SELECT count(*) AS n FROM cm.approvals WHERE payload->>'subkind'='document_review' "
            "AND payload->'data'->'document'->>'id'=%s",
            (did,),
        ).fetchone()["n"]
    assert n == 1
    assert ex.load_upload(did)["state"] == "pending_review"
    assert len({o.get("approval_id") for o in out if o.get("approval_id")}) == 1


def _aid(did: str) -> UUID:
    out = rv.run_document_extract(did)
    return UUID(out["approval_id"])


def test_concurrent_double_approve_writes_once(pts: dict) -> None:
    did = _txt_doc(A, "Lab report zzraceapprove smear negative 2026-10-12")
    aid = _aid(did)
    doc = _doctor()
    out = race(
        [
            lambda: decide(aid, ReviewDecisionIn(action="approve"), via="console", actor_id=doc)
            for _ in range(4)
        ]
    )
    assert not [o for o in out if isinstance(o, BaseException)], out
    assert len({o.decision_id for o in out}) == 1
    assert ex.load_upload(did)["state"] == "indexed"
    chunks = _chunks_of(did)
    assert chunks and len(chunks) == len({r["content"] for r in chunks})
    assert len(_doc_events(pts[A], did)) == 1
    assert rv.on_approved(aid, embedder=FakeEmbedder())["status"] == "duplicate"


def test_concurrent_on_approved_hooks_are_idempotent(pts: dict) -> None:
    did = _txt_doc(A, "Lab report zzracehook smear negative 2026-10-12 " + "word " * 900)
    aid = _aid(did)
    with transaction() as c:  # decision committed without the hook, as after a crash
        decide(aid, ReviewDecisionIn(action="approve"), via="console", actor_id=_doctor(), conn=c)
    out = race([lambda: rv.on_approved(aid, embedder=FakeEmbedder()) for _ in range(4)])
    errors = [o for o in out if isinstance(o, BaseException)]
    assert not errors, errors
    assert ex.load_upload(did)["state"] == "indexed"
    chunks = _chunks_of(did)
    assert len(chunks) == len({r["content"] for r in chunks}) and len(_doc_events(pts[A], did)) == 1


def test_approve_racing_reject_has_one_winner(pts: dict) -> None:
    did = _txt_doc(A, "Lab report zzraceboth smear negative 2026-10-12")
    aid = _aid(did)
    doc = _doctor()
    out = race(
        [
            lambda: decide(aid, ReviewDecisionIn(action="approve"), via="console", actor_id=doc),
            lambda: decide(
                aid,
                ReviewDecisionIn(action="reject", reason="wrong patient"),
                via="console",
                actor_id=doc,
            ),
        ]
    )
    wins = [o for o in out if not isinstance(o, BaseException)]
    losses = [o for o in out if isinstance(o, BaseException)]
    assert len(wins) == 1 and len(losses) == 1 and isinstance(losses[0], DecisionError)
    assert losses[0].code == "already_decided"
    state = ex.load_upload(did)["state"]
    if wins[0].action == "reject":
        assert state == "rejected" and _chunks_of(did) == [] and _doc_events(pts[A], did) == []
    else:
        assert state == "indexed" and _chunks_of(did)


def test_two_patients_same_bytes_concurrently_get_their_own_rows(pts: dict) -> None:
    out = race([lambda: up(A, png(900)), lambda: up(B, png(900))])
    assert all(o.reason is None and not o.duplicate for o in out)
    assert out[0].document_id != out[1].document_id
    assert [str(r["document_id"]) for r in uploads_repo.list_for_patient(A)] == [out[0].document_id]
    assert [str(r["document_id"]) for r in uploads_repo.list_for_patient(B)] == [out[1].document_id]
