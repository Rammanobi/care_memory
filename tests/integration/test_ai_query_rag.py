"""Ask box over patient memory (RAG) on caremem_test: cited answers, abstention, day 3 vs day 30, isolation.

Offline by default: FakeEmbedder + a fake chat model that cites the chunk refs it is shown. One optional
``live`` test uses the real OpenAI embedding and deepseek flash with a $0.20 governor cap.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from cm.api.main import create_app
from cm.api.routers import query as q
from cm.api.routers.auth import reset_rate_limits
from cm.contracts.agents import ToolCallUsed
from cm.core import clock
from cm.core.db import transaction
from cm.jobs import rag_index
from cm.rag.embed import FakeEmbedder
from cm.store import chunks_repo
from cm.tools import memory_search as ms

pytestmark = pytest.mark.db
WEB = {"X-CM-Client": "web"}
FAKE = FakeEmbedder()
DAY3, DAY30, REAL = "P-9001", "P-9002", "P-0142"  # fixture patients (9xxx tokens are test-only)
REF = re.compile(r"D-[0-9a-f]{8}")


class FakeChat:
    """Cites the first chunk whose line contains ``pick`` and (optionally) adds an uncited and a bad-number line."""

    def __init__(self, pick: str, sentence: str, junk: bool = True) -> None:
        self.pick, self.sentence, self.junk, self.seen = pick, sentence, junk, ""

    def invoke(self, messages: Any) -> AIMessage:
        self.seen = messages[-1].content
        line = next((x for x in self.seen.splitlines() if self.pick.lower() in x.lower() and x.startswith("[D-")), "")
        m = REF.search(line)
        if not m:
            return AIMessage(content="NOT_IN_RECORD")
        out = self.sentence.format(ref=m.group(0))
        if self.junk:
            out += " She is likely unwell. She missed 99 doses [" + m.group(0) + "]."
        return AIMessage(content=out)


def _add(conn: Any, token: str, text: str, when: Any, *, kind: str = "daily", numbers: dict[str, Any] | None = None,
         embed: bool = True) -> None:
    extra: dict[str, Any] = {"kind": kind, "chunk_kind": kind, "role": "chunk", "author": "system",
                             "source_event_ids": [hashlib.sha256(text.encode()).hexdigest()[:12]]}
    if numbers:
        extra["numbers"] = numbers
    did = chunks_repo.upsert_document({
        "patient_token": token, "doc_type": "checkin", "source": "memory", "author_role": "system",
        "occurred_at": when, "recorded_at": when, "content_hash": hashlib.sha256((token + text).encode()).digest(),
        "extra": extra}, conn=conn)
    chunks_repo.upsert_chunk({
        "document_id": did, "patient_token": token, "doc_type": "checkin", "occurred_at": when, "recorded_at": when,
        "content": text, "content_hash": hashlib.sha256(text.encode()).digest(), "extra": extra,
        "embedding": FAKE.embed_query(text) if embed else None, "embedding_model": "fake"}, conn=conn)


@pytest.fixture()
def corpora(pinned_clock: None):
    now = clock.now()
    for t in (DAY3, DAY30, REAL):
        chunks_repo.delete_patient_index(t)
    with transaction() as conn:
        for i, t in enumerate(["Took the morning dose on time.", "Missed the evening dose after the market visit.",
                               "Reported fever and cough at night."]):
            _add(conn, DAY3, t, now - timedelta(days=3 - i))
        for i in range(70):  # day 30: retrieval path (more than 60 live chunks)
            _add(conn, DAY30, f"Day {i + 1} check-in note {i}: took the dose, nothing else to report.",
                 now - timedelta(days=30 - i // 3, hours=i))
        _add(conn, DAY30, "Week summary: 3 doses missed this week, mostly on Sundays after the market.",
             now - timedelta(days=2), kind="weekly", numbers={"missed_7d": 3, "taken_7d": 4})
        _add(conn, REAL, "Missed the evening dose after the market visit.", now - timedelta(days=4))
        _add(conn, REAL, "Said the cough is better and asked for a refill.", now - timedelta(days=1))
    yield now
    for t in (DAY3, DAY30, REAL):
        chunks_repo.delete_patient_index(t)


@pytest.fixture()
def doctor(pinned_clock: None) -> TestClient:
    reset_rate_limits()
    c = TestClient(create_app(), headers=WEB)
    pw = json.loads(os.environ["DEMO_USER_PASSWORDS"])["dr.rao"]
    assert c.post("/auth/login", json={"username": "dr.rao", "password": pw}).status_code == 200
    return c


def _rag(code: str, day: int, question: str, now: Any, *, llm: bool) -> tuple[q.RagOutcome | None, list[ToolCallUsed]]:
    calls: list[ToolCallUsed] = []
    with transaction() as conn:
        return q.rag_answer(code, day, question, now, conn, calls, use_llm=llm), calls


@pytest.fixture()
def llm_on(monkeypatch):
    monkeypatch.setattr(q, "llm_available", lambda: True)
    monkeypatch.setattr(q, "_embedder", lambda: FAKE)


# ------------------------------------------------------------------ the Ask box over HTTP
def test_http_extractive_answer_cites_chunks_without_llm(doctor, corpora):
    r = doctor.post("/query", json={"question": "Did PT-0142 miss the evening dose after the market?"}).json()
    assert REF.search(r["answer_text"]) and "Missed the evening dose" in r["answer_text"]
    call = r["tool_calls_used"][0]
    assert call["tool"] == "search_patient_memory" and call["args"]["patient"] == "PT-0142"
    row = call["result_preview"][0]
    assert set(row) == {"ref", "date", "kind", "snippet"} and row["ref"] in r["answer_text"]
    assert r["numbers_verified"] is True and r["refused"] is False


def test_http_llm_answer_is_composed_from_chunks_and_cut_to_cited(doctor, corpora, monkeypatch, llm_on):
    chat = FakeChat("market", "Missed the evening dose after the market visit [{ref}].")
    monkeypatch.setattr(q, "_worker_chat", lambda: chat)
    r = doctor.post("/query", json={"question": "Why did PT-0142 miss a dose?"}).json()
    assert r["answer_text"].startswith("Missed the evening dose") and "unwell" not in r["answer_text"]
    assert "99" not in r["answer_text"]  # uncited and ungrounded sentences were cut
    cited = set(REF.findall(r["answer_text"]))
    assert cited == {x["ref"] for x in r["tool_calls_used"][0]["result_preview"]}
    assert "PT-0142" not in chat.seen.split("Question:")[0]  # chunks carry no patient code


def test_http_status_chip_keeps_the_legacy_answer(doctor, corpora):
    r = doctor.post("/query", json={"question": "Why is PT-0142 flagged?"}).json()
    assert r["tool_calls_used"][0]["tool"] == "get_patient"


def test_http_unindexed_patient_uses_legacy_answer(doctor, corpora):
    r = doctor.post("/query", json={"question": "Did PT-0176 report any fever?"}).json()
    assert r["tool_calls_used"] and r["tool_calls_used"][0]["tool"] == "get_patient"


def test_http_list_questions_keep_the_canned_router(doctor, corpora):
    r = doctor.post("/query", json={"question": "Who has gone quiet?"}).json()
    assert r["tool_calls_used"][0]["tool"] == "list_patients"


# ------------------------------------------------------------------ abstention
def test_abstains_when_retrieval_finds_nothing(corpora):
    out, calls = _rag(DAY3.replace("P-", "PT-"), 3, "Did she mention quantum chromodynamics?", corpora, llm=False)
    assert out.text == q.ABSTAIN_TEXT and calls[0].row_count == 0 and calls[0].result_preview == []


def test_abstains_when_no_sentence_survives_cite_or_cut(corpora, monkeypatch, llm_on):
    monkeypatch.setattr(q, "_worker_chat", lambda: type("C", (), {
        "invoke": lambda self, m: AIMessage(content="She seems fine. Nothing to worry about.")})())
    out, _ = _rag("PT-9001", 3, "Did she miss a dose?", corpora, llm=True)
    assert out.text == q.ABSTAIN_TEXT


def test_model_may_decline_with_not_in_record(corpora, monkeypatch, llm_on):
    monkeypatch.setattr(q, "_worker_chat", lambda: FakeChat("zzz-nothing", "x"))
    assert _rag("PT-9001", 3, "Did she miss a dose?", corpora, llm=True)[0].text == q.ABSTAIN_TEXT


def test_question_about_another_patient_abstains_without_a_model_call(corpora, monkeypatch, llm_on):
    def boom() -> Any:
        raise AssertionError("no model call expected")

    monkeypatch.setattr(q, "_worker_chat", boom)
    out, calls = _rag("PT-9001", 3, "Did she miss doses like PT-0203 did?", corpora, llm=True)
    assert out.text == q.ABSTAIN_TEXT and out.why == "other_patient" and calls[0].row_count == 0


# ------------------------------------------------------------------ day 3 versus day 30
PATTERN_Q = "Which days of the week does she usually miss doses?"


def test_day3_abstains_on_pattern_question_day30_answers_with_verified_numbers(corpora, monkeypatch, llm_on):
    monkeypatch.setattr(q, "_worker_chat", lambda: FakeChat(
        "week summary", "She missed 3 doses that week, mostly on Sundays [{ref}]."))
    early, ecalls = _rag("PT-9001", 3, PATTERN_Q, corpora, llm=True)
    late, lcalls = _rag("PT-9002", 30, PATTERN_Q, corpora, llm=True)
    assert early.text == q.ABSTAIN_TEXT and ecalls[0].row_count == 0
    assert late.text.startswith("She missed 3 doses that week") and REF.search(late.text)
    assert "99" not in late.text and "unwell" not in late.text
    assert lcalls[0].result_preview[0]["kind"] == "weekly" and lcalls[0].args["small_corpus"] is False
    print("\nDAY 3 :", early.text, "\nDAY 30:", late.text)


def test_day30_without_a_weekly_card_also_abstains_on_patterns(corpora):
    out, _ = _rag("PT-0142", 30, PATTERN_Q, corpora, llm=False)  # indexed, but no weekly chunk yet
    assert out.text == q.ABSTAIN_TEXT


def test_large_corpus_search_is_capped_and_never_crosses_patients(corpora):
    with transaction() as conn:
        res = ms.search_memory("PT-9002", "doses missed on Sundays after the market", corpora, embedder=FAKE, conn=conn)
        other = ms.search_memory("PT-9002", "fever and cough at night", corpora, embedder=FAKE, conn=conn)
    assert not res.small_corpus and res.n_live == 71 and 1 <= len(res.hits) <= ms.DEFAULT_K
    assert any(h.kind == "weekly" for h in res.hits)
    assert not any("fever" in h.text for h in other.hits)  # P-9001's chunk never appears for P-9002


# ------------------------------------------------------------------ indexing job
def test_rag_index_job_is_idempotent(pinned_clock):
    chunks_repo.delete_patient_index(REAL)
    try:
        first = rag_index.index_patient("PT-0142", embedder=FAKE)
        again = rag_index.index_patient("PT-0142", embedder=FAKE)
        assert first.chunks_new > 0 and again.chunks_new == 0 and again.embedded == 0
        assert chunks_repo.count_chunks(REAL) == first.chunks_total
    finally:
        chunks_repo.delete_patient_index(REAL)


def test_nightly_hook_indexes_named_patients_and_survives_failures(pinned_clock):
    chunks_repo.delete_patient_index(REAL)
    try:
        out = rag_index.index_after_nightly(codes=["PT-0142", "PT-0000"], embedder=FAKE)
        assert out["failed"] == ["PT-0000"] and out["chunks_new"] > 0
    finally:
        chunks_repo.delete_patient_index(REAL)


# ------------------------------------------------------------------ live (optional, $0.20 cap)
@pytest.mark.live
def test_live_openai_embedding_and_deepseek_flash_answer(corpora, monkeypatch):
    if not (os.environ.get("OPENAI_API_KEY") and os.environ.get("DEEPSEEK_API_KEY")):
        pytest.skip("OPENAI_API_KEY / DEEPSEEK_API_KEY not set")
    from cm.core import llm
    from cm.eval.ai_eval import live_governor
    from cm.rag.embed import Embedder

    gov = live_governor(0.20)
    llm.set_governor(gov)
    try:
        spec = llm.resolve_spec("WORKER") or ""
        assert spec.startswith("deepseek:") and "flash" in spec
        emb = rag_index.EmbedAdapter(Embedder(cache_path=None))
        # re-embed the 71 fixture chunks of P-9002 with the real model (short lines, a fraction of a cent)
        with transaction() as conn:
            rows = conn.execute("SELECT chunk_id, content FROM cm.text_chunks WHERE patient_token=%s", (DAY30,)).fetchall()
            vecs = emb.embed([r["content"] for r in rows])
            for r, v in zip(rows, vecs, strict=True):
                conn.execute("UPDATE cm.text_chunks SET embedding=%s::halfvec(1536), embedding_model='live' "
                             "WHERE chunk_id=%s", ("[" + ",".join(f"{x:.6g}" for x in v) + "]", r["chunk_id"]))
        monkeypatch.setattr(q, "llm_available", lambda: True)
        monkeypatch.setattr(q, "_embedder", lambda: Embedder(cache_path=None))
        out, calls = _rag("PT-9002", 30, "Which days of the week does she usually miss doses?", corpora, llm=True)
        assert out and (out.text == q.ABSTAIN_TEXT or REF.search(out.text))
        assert gov.store.total_cost() <= 0.20
        print(f"\nLIVE answer: {out.text}\nLIVE spend: {gov.store.total_cost()!r}")
    finally:
        llm.set_governor(None)
        chunks_repo.delete_patient_index(DAY30)
