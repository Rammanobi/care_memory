"""Hybrid patient-memory retrieval (RAG_STRATEGY_v2 section 4): prefilter -> vector + BM25 -> RRF -> boosts
-> optional rerank -> MMR -> D-refs.

Design choices:
* Vector leg: exact pgvector cosine (halfvec) scan over the already-filtered rows (per-patient sets are tiny).
* Lexical leg: real BM25 (k1=1.2, b=0.75, non-negative IDF) in Python over the patient's prefiltered chunks. Postgres
  ts_rank_cd is not BM25 (no IDF saturation / length norm) and the corpus is ~30-200 chunks, so it is cheap and
  more faithful. No new dependency; search_repo.fts_search (tsvector + ts_rank_cd) stays as the SQL fallback.
* Fusion: Reciprocal Rank Fusion, k=60, equal weights. Abstain is decided on raw leg signals (cosine
  similarity, BM25 score), because RRF values are rank-only and never "low".
* Isolation: patient_token + as_of + consent + audience sensitivity are applied in SQL (cm.store.search_repo).
* rerank defaults to 'none' (owner decision).
* Pattern questions ("which weekday does the patient usually miss?") are answered by the weekly summary cards,
  but short event chunks outrank them in the vector leg and, when the question language differs from the card
  language (Telugu question, English cards), neither leg ranks them. ``pattern=True`` therefore guarantees a
  small quota of weekly cards in the final list (``with_rollup_quota``), taken from the whole prefiltered pool.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from cm.core.tokenize import tokenize
from cm.rag import rerank as _rerank
from cm.rag.embed import Embedder, FakeEmbedder
from cm.store import search_repo as repo

Mode = Literal["vector", "bm25", "hybrid"]
Rerank = Literal["none", "llm", "cross"]

RRF_K = 60
LEG_TOP = 40
MMR_LAMBDA = 0.7
ABSTAIN_MIN_SIM = 0.25  # cosine; text-embedding-3-small unrelated text is typically < 0.2
BM25_K1, BM25_B = 1.2, 0.75
ROLLUP_KINDS = ("weekly",)
ROLLUP_QUOTA = 4  # weekly cards guaranteed in the final list of a pattern question (when that many exist)
ALL_SENSITIVITIES = ("normal", "hiv_adjacent", "mental_health")
_WORD = re.compile(r"\w+", re.UNICODE)


@dataclass
class Hit:
    ref: str  # D-xxxxxxxx (first 8 hex of chunk_id)
    chunk_id: Any
    document_id: Any
    doc_type: str
    occurred_at: datetime | None
    recorded_at: datetime
    sensitivity: str
    text: str
    extra: dict[str, Any]
    score: float = 0.0
    parts: dict[str, float] = field(default_factory=dict)
    emb: list[float] | None = field(default=None, repr=False)

    @property
    def when(self) -> datetime:
        return self.occurred_at or self.recorded_at


@dataclass
class SearchResult:
    hits: list[Hit]
    abstain: bool
    mode: str
    rerank: str
    best: dict[str, float]
    timings_ms: dict[str, float]
    notes: list[str] = field(default_factory=list)


def ref_of(chunk_id: Any) -> str:
    return "D-" + str(chunk_id).replace("-", "")[:8]


def tokens(text: str) -> list[str]:
    return [t.lower() for t in _WORD.findall(text)]


# ---------- pure helpers (unit-tested without a database) ----------
def bm25_scores(query: str, docs: list[str]) -> list[float]:
    """BM25 (k1=1.2, b=0.75) with the Lucene non-negative IDF log(1 + (N-n+.5)/(n+.5)).

    Hand-rolled (not rank_bm25's Okapi) because Okapi's IDF goes <= 0 for terms in half the docs, which is
    common in a tiny per-patient corpus and would make real matches look like misses. 0 means no term match.
    """
    if not docs:
        return []
    corp = [tokens(d) for d in docs]
    n = len(corp)
    avg = (sum(len(c) for c in corp) / n) or 1.0
    df: dict[str, int] = {}
    for c in corp:
        for t in set(c):
            df[t] = df.get(t, 0) + 1
    q = list(dict.fromkeys(tokens(query)))
    out = []
    for c in corp:
        tf: dict[str, int] = {}
        for t in c:
            tf[t] = tf.get(t, 0) + 1
        sc = 0.0
        for t in q:
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                f = tf[t]
                sc += idf * f * (BM25_K1 + 1) / (f + BM25_K1 * (1 - BM25_B + BM25_B * len(c) / avg))
        out.append(sc)
    return out


def rrf(rankings: dict[str, list[Any]], *, k: int = RRF_K, weights: dict[str, float] | None = None
        ) -> dict[Any, tuple[float, dict[str, int]]]:
    """score(id) = sum_leg w_leg / (k + rank), rank from 1. Returns {id: (score, {leg: rank})}."""
    out: dict[Any, tuple[float, dict[str, int]]] = {}
    for leg, ids in rankings.items():
        w = (weights or {}).get(leg, 1.0)
        for r, i in enumerate(ids, start=1):
            s, ranks = out.get(i, (0.0, {}))
            ranks = {**ranks, leg: r}
            out[i] = (s + w / (k + r), ranks)
    return out


def cosine(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb) if na and nb else 0.0


def jaccard(a: str, b: str) -> float:
    sa, sb = set(tokens(a)), set(tokens(b))
    return len(sa & sb) / len(sa | sb) if sa | sb else 0.0


def _sim(a: Hit, b: Hit) -> float:
    if a.emb and b.emb and len(a.emb) == len(b.emb):
        return cosine(a.emb, b.emb)
    return jaccard(a.text, b.text)


def mmr(hits: list[Hit], k: int, *, lam: float = MMR_LAMBDA, max_per_day: int = 3,
        positional: bool = False) -> list[Hit]:
    """Greedy Maximal Marginal Relevance on an already-ordered list; at most max_per_day per calendar day."""
    if not hits:
        return []
    top = max(h.score for h in hits) or 1.0
    rel = {h.ref: (1 - i / len(hits)) if positional else h.score / top for i, h in enumerate(hits)}
    chosen: list[Hit] = []
    rest = list(hits)
    per_day: dict[Any, int] = {}
    while rest and len(chosen) < k:
        best, best_v = None, -math.inf
        for h in rest:
            if per_day.get(h.when.date(), 0) >= max_per_day:
                continue
            div = max((_sim(h, c) for c in chosen), default=0.0)
            v = lam * rel[h.ref] - (1 - lam) * div
            if v > best_v:
                best, best_v = h, v
        if best is None:
            break
        best.parts["mmr"] = round(best_v, 6)
        chosen.append(best)
        rest.remove(best)
        per_day[best.when.date()] = per_day.get(best.when.date(), 0) + 1
    return chosen


def with_rollup_quota(final: list[Any], candidates: list[Any], kind_of: Any, *, quota: int = ROLLUP_QUOTA,
                      kinds: tuple[str, ...] = ROLLUP_KINDS) -> list[Any]:
    """Guarantee at least ``quota`` rollup-kind items in ``final`` (best-first), keeping its length.

    ``candidates`` are further rollup items, best first. Missing slots are filled from them and paid for by the
    lowest-ranked non-rollup items of ``final``; they are placed after the first two items. Pure; items are any objects ``kind_of`` can classify.
    """
    have = [h for h in final if kind_of(h) in kinds]
    seen = {id(h) for h in final}
    extra = [h for h in candidates if kind_of(h) in kinds and id(h) not in seen][: max(0, quota - len(have))]
    if not extra:
        return list(final)
    out = list(final)
    for _ in extra:  # drop from the tail: the lowest-ranked non-rollup item
        for i in range(len(out) - 1, -1, -1):
            if kind_of(out[i]) not in kinds:
                del out[i]
                break
    return out[:2] + extra + out[2:]  # right after the two best, so a caller's tail cut never drops them


def _kind(h: Hit) -> str:
    return str((h.extra or {}).get("kind") or "event")


def recency_boost(h: Hit, as_of: datetime) -> float:
    age = max(0.0, (as_of - h.when).total_seconds() / 86400)
    return 1 + 0.1 * math.exp(-age / 14)


def decide_abstain(mode: str, best_sim: float | None, best_bm25: float | None, *,
                   min_sim: float = ABSTAIN_MIN_SIM) -> bool:
    """Abstain when every active leg is weak: cosine below min_sim and no positive BM25 term match."""
    sim_ok = best_sim is not None and best_sim >= min_sim
    lex_ok = best_bm25 is not None and best_bm25 > 0
    if mode == "vector":
        return not sim_ok
    if mode == "bm25":
        return not lex_ok
    return not (sim_ok or lex_ok)


# ---------- orchestration ----------
def _hit(r: dict[str, Any]) -> Hit:
    return Hit(ref=ref_of(r["chunk_id"]), chunk_id=r["chunk_id"], document_id=r["document_id"],
               doc_type=r["doc_type"], occurred_at=r["occurred_at"], recorded_at=r["recorded_at"],
               sensitivity=r["sensitivity"], text=r["content"], extra=r["extra"] or {}, emb=r.get("emb"))


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)


def _apply_pattern_quota(f: Any, final: list[Hit], by_id: dict[Any, Hit], top_k: int, abstain: bool,
                         notes: list[str], mode: str, conn: Any) -> tuple[list[Hit], bool]:
    """Pattern question: pull weekly cards from the whole prefiltered pool (fused score, then newest first)."""
    have = {h.chunk_id for h in final}
    cands = []
    for r in repo.fetch_pool(f, conn=conn):  # newest first
        if r["chunk_id"] in have or (r["extra"] or {}).get("role") == "parent":
            continue
        cands.append(by_id.get(r["chunk_id"]) or _hit(r))
    cands.sort(key=lambda h: -h.score)  # stable: ties keep newest first
    out = with_rollup_quota(final, cands, _kind)[:max(top_k, len(final))]
    added = [h for h in out if h.chunk_id not in have]
    if not added:
        return final, abstain
    for h in added:
        h.parts["rollup_quota"] = 1.0
    notes.append(f"pattern question: {len(added)} weekly card(s) added by quota")
    return out, False  # weekly cards are the evidence for a pattern; cite-or-cut still guards the answer


def search_patient_memory(  # noqa: PLR0913, PLR0915
    patient_token: str, query: str, as_of: datetime, *, top_k: int = 8, mode: Mode = "hybrid",
    rerank: Rerank = "none", audience: Literal["doctor", "patient", "supporter"] = "doctor",
    doc_types: list[str] | None = None, date_from: datetime | None = None, date_to: datetime | None = None,
    consent: bool = True, recency: bool = False, embedder: Embedder | FakeEmbedder | None = None,
    min_sim: float = ABSTAIN_MIN_SIM, mmr_lambda: float = MMR_LAMBDA, max_per_day: int = 3,
    pattern: bool = False, conn: Any = None,
) -> SearchResult:
    if mode not in ("vector", "bm25", "hybrid"):
        raise ValueError(f"unknown mode {mode}")
    if rerank not in ("none", "llm", "cross"):
        raise ValueError(f"unknown rerank {rerank}")
    t_all = time.perf_counter()
    tm: dict[str, float] = {}
    notes: list[str] = []
    f = repo.SearchFilter(patient_token, as_of, ALL_SENSITIVITIES if audience == "doctor" else ("normal",),
                          doc_types, date_from, date_to, consent)
    legs: dict[str, list[Any]] = {}
    by_id: dict[Any, Hit] = {}
    best_sim = best_bm25 = None

    if mode in ("vector", "hybrid"):
        try:
            t0 = time.perf_counter()
            emb = embedder or Embedder()
            qv = emb.embed_query(tokenize(query))
            tm["embed_ms"] = _ms(t0)
            t0 = time.perf_counter()
            rows = repo.vector_search(f, qv, limit=LEG_TOP, conn=conn)
            tm["vector_ms"] = _ms(t0)
            for r in rows:
                h = by_id.setdefault(r["chunk_id"], _hit(r))
                h.emb, h.parts["vec_sim"] = r["emb"], round(r["sim"], 6)
            legs["vec"] = [r["chunk_id"] for r in rows]
            best_sim = rows[0]["sim"] if rows else None
        except Exception as e:  # noqa: BLE001 - hybrid degrades to BM25-only; vector mode must fail loud
            if mode == "vector":
                raise
            notes.append(f"vector leg skipped: {type(e).__name__}")
            mode = "bm25"

    if mode in ("bm25", "hybrid"):
        t0 = time.perf_counter()
        pool = repo.fetch_pool(f, conn=conn)
        sc = bm25_scores(query, [r["content"] for r in pool])
        ranked = sorted(((s, r) for s, r in zip(sc, pool, strict=True) if s > 0), key=lambda x: -x[0])[:LEG_TOP]
        best_bm25 = ranked[0][0] if ranked else 0.0
        for s, r in ranked:
            h = by_id.setdefault(r["chunk_id"], _hit(r))
            h.parts["bm25"] = round(s, 6)
        legs["bm25"] = [r["chunk_id"] for _, r in ranked]
        tm["bm25_ms"] = _ms(t0)

    t0 = time.perf_counter()
    fused = rrf(legs)
    for cid, (s, ranks) in fused.items():
        h = by_id[cid]
        h.parts["rrf"] = round(s, 6)
        for leg, rk in ranks.items():
            h.parts[f"{leg}_rank"] = float(rk)
        h.score = s * (recency_boost(h, as_of) if recency else 1.0)
        if recency:
            h.parts["recency"] = round(recency_boost(h, as_of), 4)
    ordered = sorted(by_id.values(), key=lambda h: (-h.score, h.ref))
    tm["fuse_ms"] = _ms(t0)

    if rerank != "none" and ordered:
        t0 = time.perf_counter()
        fn = _rerank.llm_rerank if rerank == "llm" else _rerank.cross_rerank
        ordered, note = fn(query, ordered)
        notes.append(note)
        tm["rerank_ms"] = _ms(t0)

    if mode == "hybrid" and ordered:  # BM25-only hits have no embedding yet: fetch for MMR similarity
        miss = [h.chunk_id for h in ordered[:LEG_TOP] if h.emb is None]
        if miss:
            embs = repo.fetch_embeddings(miss, f, conn=conn)
            for h in ordered:
                if h.emb is None and h.chunk_id in embs:
                    h.emb = embs[h.chunk_id]

    t0 = time.perf_counter()
    final = mmr(ordered, top_k, lam=mmr_lambda, max_per_day=max_per_day, positional=rerank != "none")
    tm["mmr_ms"] = _ms(t0)
    abstain = decide_abstain(mode, best_sim, best_bm25, min_sim=min_sim) or not final
    if pattern and final:
        final, abstain = _apply_pattern_quota(f, final, by_id, top_k, abstain, notes, mode, conn)
    tm["total_ms"] = _ms(t_all)
    return SearchResult(final, abstain, mode, rerank,
                        {k: v for k, v in (("vec_sim", best_sim), ("bm25", best_bm25)) if v is not None},
                        tm, notes)
