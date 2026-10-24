"""Patient-memory search tool (RAG_STRATEGY_v2 5.1): a thin, safe wrapper over ``cm.rag.retrieve``.

Rules baked in here (none of them is a choice the model gets to make):
* the patient token is bound server-side (``code`` comes from the request, never from model arguments);
* audience is always ``doctor`` (the Ask box is doctor-only); rerank is always ``none`` (owner ruling);
* defaults from RAG_RESEARCH_NOTES section 7: hybrid, top_k 12, MMR lambda 0.7, at most 3 chunks per day,
  recency boost only when the question asks for the latest/last/recent;
* small-corpus switch: a patient with at most ``SMALL_CORPUS`` live chunks gets ALL of them (no MMR, no rerank);
* parent chunks (``extra.role == 'parent'``) are context carriers only and are never returned;
* context order is date ascending, with the two best-scoring chunks listed in ``key_refs``.

SQL lives in ``cm.store``; this module only orchestrates and shapes the result.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from cm.rag import retrieve as _retrieve
from cm.store import search_repo as _repo

DEFAULT_K = 12
SMALL_CORPUS = 60
MMR_LAMBDA = 0.7
MAX_PER_DAY = 3
KEY_EVIDENCE = 2
MIN_PATTERN_DAYS = 7  # a weekly pattern needs at least one closed week

_CODE = re.compile(r"\bP(?:T)?-\d{4}\b", re.I)
_RECENT = re.compile(r"\b(latest|last|lately|recent(?:ly)?|most recent|newest|today|yesterday|now)\b", re.I)
_PATTERN = re.compile(
    r"\b(pattern|patterns|usually|typically|tend|tends|often|always|trend|trends|habit|habits|recurr\w*|"
    r"regularly|which days?|what days?|weekdays?|weekends?|most (?:often|days)|every (?:week|monday|tuesday|"
    r"wednesday|thursday|friday|saturday|sunday)|over time|week over week)\b",
    re.I,
)


@dataclass
class ChunkHit:
    ref: str  # D-xxxxxxxx
    date: str  # ISO date of the event or window
    source: str
    author_role: str
    kind: str  # event | window | daily | weekly
    text: str
    event_refs: list[str]
    score: float
    numbers: dict[str, Any] = field(default_factory=dict)
    sensitivity: str = "normal"


@dataclass
class MemoryResult:
    hits: list[ChunkHit]
    abstain: bool
    mode: str  # all | hybrid | bm25 | vector
    n_live: int
    small_corpus: bool
    key_refs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    best: dict[str, float] = field(default_factory=dict)
    kinds_live: dict[str, int] = field(default_factory=dict)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(h) for h in self.hits]


# Telugu has no reliable \b, so these are plain substrings: usually, which day, often, always, pattern, every week
_PATTERN_TE = ("సాధారణంగా", "ఏ రోజు", "ఏ రోజుల", "తరచుగా", "ఎప్పుడూ", "నమూనా", "ప్యాటర్న్", "ప్రతి వారం")


def is_pattern_question(question: str) -> bool:
    return bool(_PATTERN.search(question)) or any(t in question for t in _PATTERN_TE)


def asks_recent(question: str) -> bool:
    return bool(_RECENT.search(question))


def clean_query(question: str) -> str:
    """The question without the patient code (the code is routing, not content)."""
    return _CODE.sub(" ", question).strip() or question


def token_of(code: str) -> str:
    """'PT-0142' or 'P-0142' -> 'P-0142'. Raises ValueError for anything else (checked again in SQL)."""
    c = (code or "").strip().upper()
    if re.fullmatch(r"PT-\d{4}", c):
        return "P-" + c[3:]
    if re.fullmatch(r"P-\d{4}", c):
        return c
    raise ValueError("patient code must look like PT-0142")


def _is_parent(h: Any) -> bool:
    return (h.extra or {}).get("role") == "parent"


def _event_refs(extra: dict[str, Any]) -> list[str]:
    return ["E-" + str(i).replace("-", "")[:8] for i in (extra.get("source_event_ids") or [])]


def _numbers(extra: dict[str, Any]) -> dict[str, Any]:
    n = extra.get("numbers") or {}
    return {k: v for k, v in n.items() if isinstance(v, int | float) and not isinstance(v, bool)}


def _shape(h: Any) -> ChunkHit:
    x = h.extra or {}
    return ChunkHit(
        ref=h.ref,
        date=h.when.date().isoformat(),
        source=h.doc_type,
        author_role=str(x.get("author") or "system"),
        kind=str(x.get("kind") or "event"),
        text=h.text,
        event_refs=_event_refs(x),
        score=round(float(h.score or 0.0), 6),
        numbers=_numbers(x),
        sensitivity=h.sensitivity,
    )


def _dedupe(hits: list[Any]) -> list[Any]:
    """Drop a lower-ranked chunk that repeats the same source events with the same kind."""
    seen: set[tuple[str, tuple[str, ...]]] = set()
    out = []
    for h in hits:
        x = h.extra or {}
        key = (str(x.get("kind")), tuple(sorted(str(i) for i in x.get("source_event_ids") or [])))
        if key[1] and key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def _live_pool(patient_token: str, as_of: datetime, consent: bool, conn: Any) -> list[Any]:
    f = _repo.SearchFilter(patient_token, as_of, _retrieve.ALL_SENSITIVITIES, None, None, None, consent)
    return [_retrieve._hit(r) for r in _repo.fetch_pool(f, conn=conn)]  # noqa: SLF001 - shared row shaper


def _kinds(pool: list[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for h in pool:
        k = str((h.extra or {}).get("kind") or "event")
        out[k] = out.get(k, 0) + 1
    return out


def search_memory(  # noqa: PLR0913
    code: str,
    question: str,
    as_of: datetime,
    *,
    k: int = DEFAULT_K,
    mode: str = "hybrid",
    embedder: Any = None,
    consent: bool = True,
    conn: Any = None,
) -> MemoryResult:
    """Search one patient's memory. ``code`` is trusted server input (PT-0142 or P-0142)."""
    token = token_of(code)
    pool = [h for h in _live_pool(token, as_of, consent, conn) if not _is_parent(h)]
    kinds = _kinds(pool)
    if not pool:
        return MemoryResult([], True, "all", 0, False, notes=["no indexed chunks"], kinds_live=kinds)
    if len(pool) <= SMALL_CORPUS:  # small-corpus switch: send everything, oldest first
        ordered = sorted(pool, key=lambda h: (h.when, h.ref))
        return MemoryResult([_shape(h) for h in ordered], False, "all", len(pool), True, kinds_live=kinds)
    res = _retrieve.search_patient_memory(
        token, clean_query(question), as_of, top_k=k + 4, mode=mode, rerank="none", audience="doctor",
        consent=consent, recency=asks_recent(question), embedder=embedder, mmr_lambda=MMR_LAMBDA,
        max_per_day=MAX_PER_DAY, pattern=is_pattern_question(question), conn=conn,
    )
    hits = _dedupe([h for h in res.hits if not _is_parent(h)])[:k]
    key = [h.ref for h in sorted(hits, key=lambda h: -h.score)[:KEY_EVIDENCE]]
    ordered = sorted(hits, key=lambda h: (h.when, h.ref))
    return MemoryResult(
        [_shape(h) for h in ordered], bool(res.abstain or not hits), res.mode, len(pool), False,
        key_refs=key, notes=list(res.notes), best=dict(res.best), kinds_live=kinds,
    )


def as_langchain_tool(code: str, as_of: datetime, *, embedder: Any = None, conn: Any = None) -> Any:
    """A model-callable tool whose only argument is the query. The patient is fixed here, server-side."""
    from langchain_core.tools import StructuredTool
    from pydantic import create_model

    def search_patient_memory(query: str) -> str:
        import json

        r = search_memory(code, query, as_of, embedder=embedder, conn=conn)
        return json.dumps({"abstain": r.abstain, "chunks": r.as_dicts()}, default=str)

    return StructuredTool.from_function(
        search_patient_memory,
        name="search_patient_memory",
        description="Search this patient's own record. Returns dated chunks with D- refs.",
        args_schema=create_model("MemorySearchArgs", query=(str, ...)),
    )


__all__ = [
    "ChunkHit", "MemoryResult", "as_langchain_tool", "asks_recent", "clean_query", "is_pattern_question",
    "search_memory", "token_of", "MIN_PATTERN_DAYS", "SMALL_CORPUS",
]
