"""Lane K: build the per-patient RAG index (documents + text_chunks) from the event log, idempotently.

Pipeline: events visible at ``as_of`` -> render (name-free sentences) -> tokenize + assert_clean -> chunk ->
embed (injected callable) -> upsert through ``cm.store.chunks_repo``. Rollup (daily and weekly) cards come from
``cm.memory`` features only. Re-running with the same arguments adds nothing (unique content hashes).

Schema Option A (RAG_STRATEGY_v2.md 3.2): no migration; ``extra`` carries kind, chunk_kind, source_event_ids
and window. Parent chunks (long text only) have ``extra.role = 'parent'`` and no embedding; retrieval should
filter them out and use them only for context expansion.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from cm.core.tokenize import assert_clean, tokenize
from cm.rag import chunk as _chunk
from cm.rag.render import RENDER_VERSION, Rendered, RollupCard, build_rollup_cards, render_event
from cm.store import ai_repo, chunks_repo, events_repo

EMBED_BATCH = 64
CONVERSATION_GAP = timedelta(hours=24)
_TELUGU = re.compile(r"[ఀ-౿]")


class Embedder(Protocol):
    """Anything with ``embed(texts) -> list[list[float]]`` (1536 dims). Optional ``model`` attribute is stored."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass
class IndexStats:
    patient_token: str
    as_of: datetime
    strategy: str
    documents: int = 0
    chunks_total: int = 0
    chunks_new: int = 0
    embedded: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)


@dataclass
class _Spec:
    doc: dict[str, Any]
    chunks: list[_chunk.Chunk]
    embed: bool
    kind: str
    window: dict[str, str] | None = None
    numbers: dict[str, Any] | None = None
    cites: dict[str, list[str]] | None = None


def _sha(*parts: str) -> bytes:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).digest()


def _clean(text: str) -> str:
    out = tokenize(text)
    assert_clean(out)
    return out


def _lang(text: str) -> str:
    return "te" if _TELUGU.search(text) else "en"


def _doc_row(
    token: str,
    kind: str,
    text: str,
    ids: list[str],
    *,
    doc_type: str,
    source: str,
    role: str,
    occurred_at: datetime,
    recorded_at: datetime,
    consent_id: Any,
    extra: dict[str, Any],
) -> dict[str, Any]:
    real_role = role
    if consent_id is None:  # documents CHECK: no consent means the system authored the index row
        role = "system"
    return {
        "patient_token": token,
        "doc_type": doc_type,
        "source": {"chemist": "chemist_feed", "lab": "upload"}.get(source, source),
        "author_role": role,
        "occurred_at": occurred_at,
        "recorded_at": recorded_at,
        "consent_id": consent_id,
        "language": _lang(text),
        "extraction_model": RENDER_VERSION,
        "content_hash": _sha(token, kind, ",".join(ids), text),
        "extra": {
            **extra,
            "kind": kind,
            "chunk_kind": kind,
            "source_event_ids": ids,
            "author": real_role,
            "render_version": RENDER_VERSION,
        },
    }


def _event_spec(r: Rendered, token: str, strategy: str, size: int, overlap: int) -> _Spec:
    text = _clean(r.text)
    doc = _doc_row(
        token,
        "event",
        text,
        [r.event_id],
        doc_type=r.doc_type,
        source=r.source,
        role=r.author_role,
        occurred_at=r.occurred_at,
        recorded_at=r.recorded_at,
        consent_id=r.consent_id,
        extra={"event_type": r.event_type},
    )
    chunks = _chunk.chunk_text(text, size_tokens=size, overlap_tokens=overlap, strategy=strategy)
    return _Spec(doc, chunks, r.embed, "event")


def _rollup_spec(c: RollupCard, token: str) -> _Spec:
    text = _clean(c.text)
    start, end = c.window_start.isoformat(), c.window_end.isoformat()
    doc = _doc_row(
        token,
        c.kind,
        text,
        c.source_event_ids,
        doc_type="checkin",
        source="memory",
        role="system",
        occurred_at=c.window_start,
        recorded_at=c.window_end,
        consent_id=None,
        extra={"window": {"start": start, "end": end}, "numbers": c.numbers, "cites": c.cites},
    )
    return _Spec(
        doc,
        _chunk.chunk_text(text, strategy="event"),
        True,
        c.kind,
        {"start": start, "end": end},
        c.numbers,
        c.cites,
    )


def _conversation_specs(notes: list[Rendered], token: str, size: int) -> list[_Spec]:
    """Sliding windows (6 messages, overlap 2) over consecutive patient/supporter texts less than 24 h apart."""
    groups: list[list[Rendered]] = []
    for r in notes:
        if groups and r.occurred_at - groups[-1][-1].occurred_at <= CONVERSATION_GAP:
            groups[-1].append(r)
        else:
            groups.append([r])
    out: list[_Spec] = []
    for g in (g for g in groups if len(g) > 1):
        msgs = [
            _clean(f"{'Supporter' if r.author_role == 'supporter' else 'Patient'}: {r.text}")
            for r in g
        ]
        for i, j in _chunk.message_windows(msgs, size_tokens=size):
            part = g[i:j]
            text = "\n".join(msgs[i:j])
            ids = [r.event_id for r in part]
            win = {
                "start": part[0].occurred_at.isoformat(),
                "end": part[-1].occurred_at.isoformat(),
            }
            doc = _doc_row(
                token,
                "window",
                text,
                ids,
                doc_type="checkin",
                source=part[0].source,
                role=part[0].author_role,
                occurred_at=part[-1].occurred_at,
                recorded_at=max(r.recorded_at for r in part),
                consent_id=part[0].consent_id,
                extra={"window": win, "messages": len(part)},
            )
            out.append(_Spec(doc, _chunk.chunk_text(text, strategy="event"), True, "window", win))
    return out


def _visible(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    superseded = {e["supersedes"] for e in events if e.get("supersedes")}
    return sorted(
        (e for e in events if e["event_id"] not in superseded),
        key=lambda e: (e["occurred_at"], e["recorded_at"], str(e["event_id"])),
    )


def _specs(
    token: str,
    events: list[dict[str, Any]],
    as_of: datetime,
    strategy: str,
    size: int,
    overlap: int,
    rollups: bool,
    day0: Any,
) -> list[_Spec]:
    live = _visible(events)
    rendered = [r for e in live if (r := render_event(e, token)) is not None]
    specs = [_event_spec(r, token, strategy, size, overlap) for r in rendered]
    if strategy == "dynamic":
        notes = [
            r
            for r in rendered
            if r.event_type == "ContextNote" and r.author_role in ("patient", "supporter")
        ]
        specs += _conversation_specs(notes, token, size)
    if rollups:
        specs += [_rollup_spec(c, token) for c in build_rollup_cards(live, as_of, token, day0)]
    return specs


def _write(
    specs: list[_Spec],
    token: str,
    strategy: str,
    embedder: Embedder | None,
    embed_all: bool,
    stats: IndexStats,
    conn: Any,
) -> None:
    doc_ids = [chunks_repo.upsert_document(s.doc, conn=conn) for s in specs]
    have = chunks_repo.embedded_chunk_keys(doc_ids, conn=conn)
    todo: list[tuple[int, int, str]] = []  # (spec index, chunk index, text)
    rows: list[list[dict[str, Any]]] = []
    for si, (s, did) in enumerate(zip(specs, doc_ids, strict=True)):
        group: list[dict[str, Any]] = []
        for ci, c in enumerate(s.chunks):
            h = _sha(c.text)
            row: dict[str, Any] = {
                "document_id": did,
                "patient_token": token,
                "doc_type": s.doc["doc_type"],
                "occurred_at": s.doc["occurred_at"],
                "recorded_at": s.doc["recorded_at"],
                "consent_id": s.doc["consent_id"],
                "language": _lang(c.text),
                "content": c.text,
                "content_hash": h,
                "extra": {
                    **s.doc["extra"],
                    "strategy": strategy,
                    "role": c.role,
                    "seq": c.seq,
                    "tokens": c.tokens,
                    "tokenizer": _chunk.tokenizer_name(),
                },
            }
            group.append(row)
            if embedder and c.role == "chunk" and (s.embed or embed_all) and (did, h) not in have:
                todo.append((si, ci, c.text))
        rows.append(group)
    model = getattr(embedder, "model", None) or type(embedder).__name__
    for b in range(0, len(todo), EMBED_BATCH):
        batch = todo[b : b + EMBED_BATCH]
        vecs = embedder.embed([t for _, _, t in batch])  # type: ignore[union-attr]
        if len(vecs) != len(batch):
            raise ValueError("embedder returned the wrong number of vectors")
        for (si, ci, _), v in zip(batch, vecs, strict=True):
            rows[si][ci].update(embedding=v, embedding_model=model)
            stats.embedded += 1
    for s, group in zip(specs, rows, strict=True):
        ids: dict[int, Any] = {}
        for c, row in zip(s.chunks, group, strict=True):
            row["parent_id"] = ids.get(c.parent_seq) if c.parent_seq is not None else None
            cid, new = chunks_repo.upsert_chunk(row, conn=conn)
            ids[c.seq] = cid
            stats.chunks_total += 1
            stats.chunks_new += int(new)
            k = s.kind if c.role == "chunk" else "parent"
            stats.by_kind[k] = stats.by_kind.get(k, 0) + 1


def build_patient_index(
    patient_token: str,
    as_of: datetime,
    *,
    strategy: str = "dynamic",
    size: int = _chunk.DEFAULT_SIZE,
    overlap: int = _chunk.DEFAULT_OVERLAP,
    embedder: Embedder | None = None,
    rollups: bool = True,
    embed_all: bool = False,
    conn: Any = None,
) -> IndexStats:
    """Index one patient's events visible at ``as_of``. Safe to re-run; never duplicates.

    ``embed_all`` also embeds tap-only chunks (default: taps are full-text only, as in the strategy doc).
    Without an embedder every chunk is stored with ``embedding NULL`` (full-text only).
    """
    if conn is None:
        from cm.core.db import transaction

        with transaction() as c:
            return build_patient_index(
                patient_token,
                as_of,
                strategy=strategy,
                size=size,
                overlap=overlap,
                embedder=embedder,
                rollups=rollups,
                embed_all=embed_all,
                conn=c,
            )
    if strategy not in _chunk.STRATEGIES:
        raise ValueError(f"unknown chunk strategy {strategy!r}")
    pid, token = ai_repo.resolve_patient(patient_token, conn=conn)
    day0, _ = ai_repo.sim_day0(conn=conn)
    events = events_repo.query(pid, as_of, conn=conn)
    specs = _specs(token, events, as_of, strategy, size, overlap, rollups, day0)
    stats = IndexStats(token, as_of, strategy)
    stats.documents = len(specs)
    _write(specs, token, strategy, embedder, embed_all, stats, conn)
    return stats


__all__ = ["Embedder", "IndexStats", "build_patient_index"]
