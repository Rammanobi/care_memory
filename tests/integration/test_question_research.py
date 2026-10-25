"""cm.agents.question_research on caremem_test: demo patients with 6 / 60 days of mock history.

Offline by default (BM25 index, no embeddings, extractive brief or a scripted fake model). One optional
``live`` test runs the real WORKER model (deepseek flash) on PT-0960 with a $0.10 governor cap.
Read-only apart from the fixture: the research itself never writes approvals or outbox rows.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

import psycopg
import pytest
from langchain_core.messages import AIMessage

from cm.agents import question_research as qr
from cm.core.banned_lexicon import find_banned
from cm.core.db import transaction
from cm.core.ids import det_id
from cm.jobs import rag_index
from cm.jobs import seed_demo_accounts as sda
from cm.store import chunks_repo
from cm.tools import memory_search as ms

pytestmark = pytest.mark.db
CODES = ("PT-0906", "PT-0960")
PASSWORDS = {
    u: f"Pw-{u}-test-only" for u in ("demo.pt0906", "demo.pt0960")
}
MED_Q = "Can I take this tablet with my evening tea?"
FOOD_Q = "Can I eat chicken and eggs during the festival?"
TE = re.compile(r"[ఀ-౿]")


def _retry(fn: Any) -> Any:
    try:
        return fn()
    except psycopg.errors.DeadlockDetected:  # shared caremem_test: retry once
        return fn()


@pytest.fixture(scope="module")
def demo(seeded_db: None) -> Any:
    mp = pytest.MonkeyPatch()
    mp.setenv("CM_DATA_CLASS", "mock")
    mp.setenv("DEMO_ACCOUNT_PASSWORDS", json.dumps(PASSWORDS))
    as_of = sda.as_of_instant()

    def setup() -> None:
        with transaction() as conn:
            sda.apply_bundle(conn, sda.build_bundle())
        for c in CODES:
            rag_index.index_patient(c, as_of, embed=False)

    _retry(setup)
    yield as_of
    for c in CODES:
        chunks_repo.delete_patient_index(ms.token_of(c))
    mp.undo()


def _refs_of(code: str, q: str, as_of: Any) -> set[str]:
    with transaction() as conn:
        return {h.ref for h in ms.search_memory(code, q, as_of, mode="bm25", conn=conn).hits}


def _counts() -> tuple[int, int]:
    with transaction() as conn:
        a = conn.execute("SELECT count(*) AS n FROM cm.approvals").fetchone()["n"]
        o = conn.execute("SELECT count(*) AS n FROM cm.outbox").fetchone()["n"]
    return a, o


def test_day6_versus_day60_extractive(demo):
    early = qr.research_question("PT-0906", MED_Q, as_of=demo, embed=False).as_dict()
    late = qr.research_question("PT-0960", MED_Q, as_of=demo, embed=False).as_dict()
    assert early["status"] == late["status"] == "ready"
    assert early["confidence"] == "low" and any(
        "little history" in b["text"] for b in early["brief"]
    )
    assert late["confidence"] in {"medium", "high"} and not any(
        "little history" in b["text"] for b in late["brief"]
    )
    assert late["model"] == "extractive" and late["cost_usd"] == 0.0
    for r in (early, late):
        assert 3 <= len(r["brief"]) <= 6 and not find_banned(r["suggested_reply"])
    print(
        "\nDAY 3 :",
        json.dumps(early, ensure_ascii=False),
        "\nDAY 60:",
        json.dumps(late, ensure_ascii=False),
    )


def test_brief_cites_only_this_patients_chunks(demo):
    r = qr.research_question("PT-0960", FOOD_Q, as_of=demo, embed=False).as_dict()
    own = _refs_of("PT-0960", FOOD_Q, demo)
    others = _refs_of("PT-0906", FOOD_Q, demo)
    d_refs = {x for b in r["brief"] for x in b["refs"] if x.startswith("D-")}
    assert d_refs <= own and not d_refs & others


def test_as_of_hides_the_future(demo):
    early_at = demo - timedelta(
        days=55
    )  # PT-0960 started 60 days before as_of: only ~5 days visible
    r = qr.research_question("PT-0960", MED_Q, as_of=early_at, embed=False).as_dict()
    visible = _refs_of("PT-0960", MED_Q, early_at)
    assert r["status"] == "ready" and r["confidence"] == "low"
    assert {x for b in r["brief"] for x in b["refs"] if x.startswith("D-")} <= visible


@contextmanager
def _vault_lang(code: str, lang: str) -> Iterator[None]:
    """Temporarily set a demo patient's vault language (caremem_test only), restored afterwards."""
    pid = det_id("person", "P-" + code[3:])
    with transaction() as conn:
        old = conn.execute(
            "SELECT lang FROM cm.identity_vault WHERE person_id=%s", (pid,)
        ).fetchone()["lang"]
        conn.execute("UPDATE cm.identity_vault SET lang=%s WHERE person_id=%s", (lang, pid))
    try:
        yield
    finally:
        with transaction() as conn:
            conn.execute("UPDATE cm.identity_vault SET lang=%s WHERE person_id=%s", (old, pid))


def test_vault_language_drives_the_reply(demo):
    en = qr.research_question("PT-0960", FOOD_Q, as_of=demo, embed=False).as_dict()
    with _vault_lang("PT-0906", "te"):
        te = qr.research_question("PT-0906", FOOD_Q, as_of=demo, embed=False).as_dict()
        urgent = qr.research_question(
            "PT-0906", "I am vomiting blood", as_of=demo, embed=False
        ).as_dict()
    assert TE.search(te["suggested_reply"]) and not TE.search(en["suggested_reply"])
    assert urgent["priority"] == "urgent" and "108" in urgent["suggested_reply"]


def test_fake_model_with_a_telugu_vault(demo):
    class Fake:
        model_name = "fake-worker"

        def invoke(self, messages: Any) -> AIMessage:
            ref = re.search(r"\[(D-[0-9a-f]{8})\]", messages[-1].content).group(1)
            return AIMessage(
                content=json.dumps(
                    {
                        "brief": [
                            f"The record has a dated entry relevant to this question [{ref}].",
                            "Uncited claim.",
                        ],
                        "reply": "Thank you for asking. Your doctor will advise you soon.",
                    }
                )
            )

    with _vault_lang("PT-0906", "te"):
        r = qr.research_question(
            "PT-0906", MED_Q, as_of=demo, model=Fake(), embed=False
        ).as_dict()
    assert r["model"] == "fake-worker" and r["brief"][0]["refs"][0].startswith("D-")
    assert "Uncited" not in json.dumps(r) and TE.search(
        r["suggested_reply"]
    )  # English proposal -> te template


def test_research_writes_nothing(demo):
    before = _counts()
    qr.research_question("PT-0906", FOOD_Q, as_of=demo, embed=False)
    assert _counts() == before


def test_unknown_patient_fails_cleanly(demo):
    r = qr.research_question("PT-0999", FOOD_Q, as_of=demo, embed=False).as_dict()
    assert r["status"] == "failed" and r["reason"] == "unknown_patient" and r["brief"] == []
    r = qr.research_question("not-a-code", FOOD_Q, as_of=demo, embed=False).as_dict()
    assert r["status"] == "failed" and r["reason"] == "bad_patient_token"


# ------------------------------------------------------------------ live (optional, $0.10 cap)
@pytest.mark.live
def test_live_deepseek_flash_on_the_60_day_patient(demo, monkeypatch):
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set")
    from cm.core import llm
    from cm.eval.ai_eval import live_governor

    gov = live_governor(0.10)
    llm.set_governor(gov)
    monkeypatch.setattr(qr, "_llm_ready", lambda: True)
    try:
        spec = llm.resolve_spec("WORKER") or ""
        assert spec.startswith("deepseek:") and "flash" in spec
        out = {}
        for name, q in (("medicine", MED_Q), ("food", FOOD_Q)):
            r = qr.research_question("PT-0960", q, as_of=demo, embed=False).as_dict()
            assert r["status"] == "ready" and not find_banned(r["suggested_reply"])
            assert 3 <= len(r["brief"]) <= 6
            out[name] = r
        assert gov.store.total_cost() <= 0.10
        print(
            "\nLIVE:",
            json.dumps(out, ensure_ascii=False, indent=1),
            "\nLIVE spend:",
            gov.store.total_cost(),
        )
    finally:
        llm.set_governor(None)
