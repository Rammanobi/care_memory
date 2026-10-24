"""Unit tests for embed / retrieve / rerank pure logic and the governed embedding methods (no DB, no network)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from cm.core import budget
from cm.core.llm import GovernedModel
from cm.core.retry import RateLimiter
from cm.rag import rerank
from cm.rag.embed import EMBED_DIM, Embedder, EmbeddingDimError, FakeEmbedder
from cm.rag.retrieve import (
    Hit,
    bm25_scores,
    cosine,
    decide_abstain,
    mmr,
    ref_of,
    rrf,
)

ENV = {"EMBEDDING_MODEL": "openai:text-embedding-3-small"}


def _hit(i: int, text: str, score: float, day: int = 1, emb: list[float] | None = None) -> Hit:
    t = datetime(2026, 2, day, 9, tzinfo=UTC)
    return Hit(ref=f"D-{i:08x}", chunk_id=i, document_id=i, doc_type="checkin", occurred_at=t, recorded_at=t,
               sensitivity="normal", text=text, extra={}, score=score, emb=emb)


def test_ref_format() -> None:
    assert ref_of("1a2b3c4d-0000-0000-0000-000000000000") == "D-1a2b3c4d"


def test_rrf_k60_and_union() -> None:
    out = rrf({"vec": ["a", "b"], "bm25": ["b", "c"]})
    assert out["a"][0] == pytest.approx(1 / 61)
    assert out["b"][0] == pytest.approx(1 / 62 + 1 / 61)
    assert out["b"][1] == {"vec": 2, "bm25": 1}
    assert max(out, key=lambda k: out[k][0]) == "b" and set(out) == {"a", "b", "c"}


def test_bm25_ranks_matching_doc_first_and_nonmatch_not_positive() -> None:
    docs = ["missed dose after market visit", "took tablets on time", "felt fever and cough", "walked to clinic"]
    s = bm25_scores("missed dose", docs)
    assert s.index(max(s)) == 0 and s[3] <= 0
    assert bm25_scores("zzz", docs) == [0.0] * 4


def test_mmr_prefers_diverse_and_caps_per_day() -> None:
    a = _hit(1, "missed dose market", 1.0, emb=[1, 0])
    b = _hit(2, "missed dose market again", 0.95, emb=[1, 0])  # near duplicate of a
    c = _hit(3, "fever cough night", 0.7, emb=[0, 1])
    out = mmr([a, b, c], 2)
    assert [h.ref for h in out] == [a.ref, c.ref]
    same_day = [_hit(i, f"t{i} x", 1 - i / 10, day=2) for i in range(1, 6)]
    assert len(mmr(same_day, 5, max_per_day=3)) == 3


def test_mmr_jaccard_fallback_without_embeddings() -> None:
    a, b, c = _hit(1, "missed dose market", 1.0), _hit(2, "missed dose market", 0.9), _hit(3, "cough fever", 0.6)
    assert [h.ref for h in mmr([a, b, c], 2)] == [a.ref, c.ref]


def test_cosine() -> None:
    assert cosine([1, 0], [1, 0]) == pytest.approx(1) and cosine([1, 0], [0, 1]) == 0 and cosine([0, 0], [1, 1]) == 0


def test_abstain_rules() -> None:
    assert decide_abstain("hybrid", 0.1, 0.0)
    assert not decide_abstain("hybrid", 0.1, 2.0)
    assert not decide_abstain("hybrid", 0.6, 0.0)
    assert decide_abstain("bm25", 0.9, 0.0) and decide_abstain("vector", None, 5.0)
    assert not decide_abstain("vector", 0.5, None)


def test_fake_embedder_deterministic_and_similar() -> None:
    f = FakeEmbedder()
    v = f.embed_query("missed dose after market")
    assert len(v) == EMBED_DIM and v == f.embed_query("missed dose after market")
    assert cosine(v, f.embed_query("missed dose market")) > cosine(v, f.embed_query("fever cough night"))


class _Prov:
    def __init__(self, dim: int = EMBED_DIM) -> None:
        self.calls: list[list[str]] = []
        self.dim = dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[0.1] * self.dim for _ in texts]


def _governed(prov: _Prov, gov: budget.BudgetGovernor | None = None) -> GovernedModel:
    return GovernedModel("EMBEDDING", governor=gov or budget.BudgetGovernor(), env=ENV,
                         limiter=RateLimiter(10_000, 10_000_000), builder=lambda s, r: prov)


def test_governed_embed_records_usage_and_returns_vectors() -> None:
    gov = budget.BudgetGovernor()
    prov = _Prov()
    out = _governed(prov, gov).embed_documents(["hello there", "second one"], task_id="t1")
    assert len(out) == 2 and len(out[0]) == EMBED_DIM
    assert gov.store.task_cost("t1") >= 0 and gov.store.patient_tokens(gov.today(), "x") == 0
    assert gov.store.total_cost() > 0


def test_governed_embed_refuses_untokenized_pii() -> None:
    from cm.core.tokenize import PIILeak

    with pytest.raises(PIILeak):
        _governed(_Prov()).embed_documents(["call me on +91 98765 43210"])


def test_embedder_cache_batches_and_dim_check() -> None:
    prov = _Prov()
    e = Embedder(_governed(prov), model_name="m", cache_path=None, batch_size=2)
    e.embed_documents(["a one", "b two", "c three"])
    assert [len(c) for c in prov.calls] == [2, 1]
    e.embed_documents(["a  one", "b two"])  # whitespace-normalised hit: no new calls
    assert len(prov.calls) == 2 and e.api_calls == 3
    bad = Embedder(_governed(_Prov(dim=8)), model_name="m", cache_path=None)
    with pytest.raises(EmbeddingDimError):
        bad.embed_documents(["x y"])


def test_embedder_disk_cache(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = str(tmp_path / "c.sqlite")
    Embedder(_governed(_Prov()), model_name="m", cache_path=p).embed_documents(["persist me"])
    prov2 = _Prov()
    Embedder(_governed(prov2), model_name="m", cache_path=p).embed_documents(["persist me"])
    assert prov2.calls == []


def test_parse_order_strict() -> None:
    assert rerank.parse_order('{"order": [2, 1]}', 3) == [2, 1]
    assert rerank.parse_order('```json\n{"order": [1]}\n```', 3) == [1]
    assert rerank.parse_order('{"order": [9]}', 3) == []
    assert rerank.parse_order("nope", 3) == []


def test_llm_rerank_orders_and_falls_back() -> None:
    hits = [_hit(i, f"text {i}", 1.0) for i in range(1, 4)]
    m = SimpleNamespace(invoke=lambda *a, **k: SimpleNamespace(content='{"order": [3, 1]}'))
    out, note = rerank.llm_rerank("q", hits, model=m)
    assert [h.chunk_id for h in out] == [3, 1, 2] and "applied" in note
    bad = SimpleNamespace(invoke=lambda *a, **k: SimpleNamespace(content="garbage"))
    out, note = rerank.llm_rerank("q", hits, model=bad)
    assert out == hits and "skipped" in note


def test_cross_rerank_skips_without_model(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("CM_RERANK_MODEL", raising=False)
    hits = [_hit(1, "a", 1.0), _hit(2, "b", 1.0)]
    out, note = rerank.cross_rerank("q", hits)
    assert out == hits and "skipped" in note
    out, _ = rerank.cross_rerank("q", hits, scorer=lambda pairs: [0.1, 0.9])
    assert out[0].chunk_id == 2


def test_recency_timedelta_sanity() -> None:
    from cm.rag.retrieve import recency_boost

    now = datetime(2026, 2, 10, tzinfo=UTC)
    assert recency_boost(_hit(1, "x", 1, day=10), now) > recency_boost(_hit(2, "x", 1, day=1), now - timedelta(0))


def _kh(i: int, kind: str, score: float = 0.0) -> Hit:
    h = _hit(i, f"t{i}", score)
    h.extra = {"kind": kind}
    return h


def _kind_of(h: Hit) -> str:
    return h.extra["kind"]


def test_rollup_quota_fills_from_candidates_and_drops_tail_events() -> None:
    from cm.rag.retrieve import with_rollup_quota

    final = [_kh(i, "event") for i in range(1, 7)]
    weeks = [_kh(10 + i, "weekly") for i in range(6)]
    out = with_rollup_quota(final, weeks, _kind_of, quota=4)
    assert len(out) == 6 and sum(_kind_of(h) == "weekly" for h in out) == 4
    assert [h.chunk_id for h in out[:2]] == [1, 2]  # best two untouched
    assert [h.chunk_id for h in out if _kind_of(h) == "event"] == [1, 2]  # tail events 3-6 paid for the cards
    assert [h.chunk_id for h in out[2:6]] == [10, 11, 12, 13]  # cards sit right after the best two


def test_rollup_quota_counts_existing_cards_and_never_exceeds_supply() -> None:
    from cm.rag.retrieve import with_rollup_quota

    final = [_kh(1, "event"), _kh(2, "weekly"), _kh(3, "event"), _kh(4, "event")]
    two = with_rollup_quota(final, [_kh(20, "weekly")], _kind_of, quota=2)
    assert len(two) == 4 and sorted(h.chunk_id for h in two) == [1, 2, 3, 20]
    out = with_rollup_quota(final, [_kh(20, "weekly")], _kind_of, quota=4)  # only 1 spare card exists
    assert len(out) == 4 and sum(_kind_of(h) == "weekly" for h in out) == 2
    assert with_rollup_quota(final, [], _kind_of) == final  # nothing to add: unchanged
    assert with_rollup_quota(final, [final[1]], _kind_of, quota=4) == final  # a card already present is not re-added
