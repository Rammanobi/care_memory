"""Retrieval against real Postgres (caremem_test): isolation, as_of, consent, sensitivity, hybrid. Plus one live embed."""

import hashlib
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from cm.core.db import transaction
from cm.rag.embed import EMBED_DIM, FakeEmbedder
from cm.rag.retrieve import search_patient_memory
from cm.store import consent as consent_repo

T_A, T_B = "P-9001", "P-9002"
FAKE = FakeEmbedder()


def d(day: int) -> datetime:
    return datetime(2026, 2, day, 9, tzinfo=UTC)


def _vec(text: str) -> str:
    return "[" + ",".join(f"{x:.6g}" for x in FAKE.embed_query(text)) + "]"


def add(conn: Any, tok: str, text: str, day: int, *, sens: str = "normal", consent_id: Any = None,
        doc_type: str = "checkin", recorded_day: int | None = None) -> Any:
    doc = conn.execute(
        "INSERT INTO cm.documents (patient_token, doc_type, source, author_role, occurred_at, recorded_at, "
        "consent_id, content_hash, sensitivity) VALUES (%s,%s,'seed','system',%s,%s,%s,%s,%s) RETURNING document_id",
        (tok, doc_type, d(day), d(recorded_day or day), consent_id, hashlib.sha256(uuid4().bytes).digest(), sens),
    ).fetchone()["document_id"]
    return conn.execute(
        "INSERT INTO cm.text_chunks (document_id, patient_token, doc_type, occurred_at, recorded_at, consent_id, "
        "sensitivity, content, content_hash, embedding, embedding_model) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::halfvec(1536),'fake') RETURNING chunk_id",
        (doc, tok, doc_type, d(day), d(recorded_day or day), consent_id, sens, text,
         hashlib.sha256(text.encode()).digest(), _vec(text)),
    ).fetchone()["chunk_id"]


@pytest.fixture()
def corpus(seeded_db: None) -> Any:
    with transaction() as conn:
        _clean(conn)
        person = conn.execute("SELECT person_id FROM cm.persons WHERE token = 'P-0142'").fetchone()["person_id"]
        # consents are append-only: grant strictly after any earlier test's withdrawal so runs never interfere
        last = conn.execute("SELECT max(effective_at) AS m FROM cm.consents WHERE person_id = %s", (person,)).fetchone()["m"]
        t0 = max(last, d(1)) + timedelta(days=1)
        cid = consent_repo.record_consent(person, "telegram", "daily_checkin", "granted", t0, "console", conn=conn)
        ids = {
            "miss": add(conn, T_A, "missed the evening dose after the market visit", 3, consent_id=cid),
            "fever": add(conn, T_A, "fever and cough at night, felt weak", 5, consent_id=cid),
            "future": add(conn, T_A, "missed dose again on the festival day", 9, consent_id=cid),
            "hiv": add(conn, T_A, "mentioned a sensitive missed dose concern", 4, sens="hiv_adjacent", consent_id=cid),
            "other": add(conn, T_B, "missed the evening dose after the market visit", 3),
        }
    yield {"ids": ids, "person": person, "consent": cid, "t0": t0}
    with transaction() as conn:
        _clean(conn)


def _clean(conn: Any) -> None:
    conn.execute("DELETE FROM cm.documents WHERE patient_token IN (%s, %s)", (T_A, T_B))


pytestmark = pytest.mark.db
Q = "missed dose after market"


@pytest.mark.parametrize("mode", ["vector", "bm25", "hybrid"])
def test_modes_find_and_isolate(corpus: Any, mode: str) -> None:
    r = search_patient_memory(T_A, Q, d(20), mode=mode, embedder=FAKE)
    refs = {h.ref for h in r.hits}
    assert not r.abstain and r.hits[0].ref == "D-" + str(corpus["ids"]["miss"]).replace("-", "")[:8]
    assert "D-" + str(corpus["ids"]["other"]).replace("-", "")[:8] not in refs
    assert all(h.parts for h in r.hits) and r.timings_ms["total_ms"] >= 0


def test_as_of_hides_future_and_recorded_later(corpus: Any) -> None:
    early = search_patient_memory(T_A, "festival day", d(4), mode="bm25", embedder=FAKE)
    assert early.abstain and not early.hits
    late = search_patient_memory(T_A, "festival day", d(10), mode="bm25", embedder=FAKE)
    assert late.hits and "festival" in late.hits[0].text
    with transaction() as conn:  # occurred early but only recorded on day 12
        add(conn, T_A, "backfilled note about a wedding", 2, recorded_day=12)
    assert not search_patient_memory(T_A, "wedding", d(10), mode="bm25", embedder=FAKE).hits
    assert search_patient_memory(T_A, "wedding", d(13), mode="bm25", embedder=FAKE).hits


def test_audience_sensitivity(corpus: Any) -> None:
    doc = search_patient_memory(T_A, "sensitive concern", d(20), mode="bm25", audience="doctor", embedder=FAKE)
    sup = search_patient_memory(T_A, "sensitive concern", d(20), mode="bm25", audience="supporter", embedder=FAKE)
    assert any(h.sensitivity == "hiv_adjacent" for h in doc.hits)
    assert all(h.sensitivity == "normal" for h in sup.hits)


def test_consent_withdrawal_hides_chunks(corpus: Any) -> None:
    t0 = corpus["t0"]
    assert search_patient_memory(T_A, Q, t0 + timedelta(days=3), mode="bm25", embedder=FAKE).hits
    consent_repo.record_consent(corpus["person"], "telegram", "daily_checkin", "withdrawn",
                                t0 + timedelta(days=1), "console")
    r = search_patient_memory(T_A, Q, t0 + timedelta(days=3), mode="bm25", embedder=FAKE)
    assert not r.hits and r.abstain
    # before the withdrawal took effect, they were still visible
    assert search_patient_memory(T_A, Q, t0 + timedelta(hours=12), mode="bm25", embedder=FAKE).hits


def test_filters_doc_type_and_window(corpus: Any) -> None:
    with transaction() as conn:
        add(conn, T_A, "lab report hemoglobin low", 4, doc_type="lab")
    r = search_patient_memory(T_A, "report hemoglobin", d(20), mode="bm25", doc_types=["lab"], embedder=FAKE)
    assert [h.doc_type for h in r.hits] == ["lab"]
    r = search_patient_memory(T_A, "missed dose", d(20), mode="bm25", date_from=d(8), embedder=FAKE)
    assert all(h.when >= d(8) for h in r.hits) and r.hits


def test_abstain_on_unrelated_query(corpus: Any) -> None:
    assert search_patient_memory(T_A, "quantum chromodynamics", d(20), mode="bm25", embedder=FAKE).abstain


def test_bad_token_and_guideline_scope(corpus: Any) -> None:
    for bad in ("P-1", "' OR 1=1 --", None):
        with pytest.raises(ValueError):
            search_patient_memory(bad, Q, d(20), embedder=FAKE)  # type: ignore[arg-type]


@pytest.mark.live
def test_live_openai_embedding_three_sentences() -> None:
    if not os.environ.get("OPENAI_API_KEY") or not os.environ.get("EMBEDDING_MODEL"):
        pytest.skip("OPENAI_API_KEY / EMBEDDING_MODEL not set")
    from cm.core import budget, llm
    from cm.rag.embed import Embedder

    gov = budget.BudgetGovernor(budget.BudgetLimits.from_env(), budget.PriceTable.from_env())
    llm.set_governor(gov)
    try:
        emb = Embedder(llm.get_model("EMBEDDING"), cache_path=None)
        vecs = emb.embed_documents(["The patient missed the evening dose.", "Felt feverish at night.",
                                    "Visited the clinic on Friday."], task_id="live-smoke")
        assert len(vecs) == 3 and all(len(v) == EMBED_DIM for v in vecs)
        print(f"\nLIVE embed dim={len(vecs[0])} est_tokens={gov.store.total_cost()!r}")
    finally:
        llm.set_governor(None)


def test_pattern_question_gets_weekly_cards_even_without_term_match(corpus: Any) -> None:
    """Telugu-style miss: the question shares no token with the English week cards and event chunks dominate."""
    with transaction() as conn:
        for day in range(1, 10):
            add(conn, T_A, f"dose taken on morning {day} by the patient", day, consent_id=corpus["consent"])
        for i, day in enumerate((6, 7, 8)):
            cid = add(conn, T_A, f"Weekly summary week {i}: most missed doses fall on Tuesday.", day,
                      consent_id=corpus["consent"])
            conn.execute("UPDATE cm.text_chunks SET extra = %s::jsonb WHERE chunk_id = %s",
                         ('{"kind": "weekly"}', cid))
    q = "dose taken morning patient"  # lexically and semantically closest to the event chunks
    plain = search_patient_memory(T_A, q, d(20), top_k=5, embedder=FAKE)
    assert not any((h.extra or {}).get("kind") == "weekly" for h in plain.hits)
    pat = search_patient_memory(T_A, q, d(20), top_k=5, embedder=FAKE, pattern=True)
    weeks = [h for h in pat.hits if (h.extra or {}).get("kind") == "weekly"]
    assert len(weeks) == 3 and len(pat.hits) == 5 and not pat.abstain
    assert all(h.when <= d(20) for h in pat.hits)
    other = search_patient_memory(T_B, q, d(20), top_k=5, embedder=FAKE, pattern=True)
    assert not any(h.text.startswith("Weekly summary") for h in other.hits)  # patient isolation
    early = search_patient_memory(T_A, q, d(7), top_k=5, embedder=FAKE, pattern=True)
    assert all(h.when <= d(7) for h in early.hits)  # as_of: later week cards stay hidden
