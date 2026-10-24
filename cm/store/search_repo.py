"""Lane A store: patient-scoped chunk search SQL (Rule 6: raw SQL lives only in cm/store).

Every query carries the same hard prefilter: patient_token = %s (never NULL / guidelines), doc_type <> guideline,
status <> withdrawn, recorded_at <= as_of AND occurred_at <= as_of, sensitivity allowed for the audience, and
the chunk's consent not withdrawn at as_of. Pool sizes are tiny, so the vector leg is an exact scan.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from cm.core.db import transaction

PATIENT_RE = r"^P-[0-9]{4}$"


@dataclass(frozen=True)
class SearchFilter:
    patient_token: str
    as_of: datetime
    sensitivities: Sequence[str] = ("normal",)  # doctor: all three
    doc_types: Sequence[str] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None  # window on COALESCE(occurred_at, recorded_at)
    consent: bool = True
    extra_params: dict[str, Any] = field(default_factory=dict)


_COLS = ("c.chunk_id, c.document_id, c.parent_id, c.patient_token, c.doc_type, c.occurred_at, c.recorded_at, "
         "c.sensitivity, c.content, c.extra, c.language")

_CONSENT = (
    " AND (c.consent_id IS NULL OR (EXISTS (SELECT 1 FROM cm.consents k WHERE k.consent_id = c.consent_id"
    " AND k.state = 'granted') AND NOT EXISTS (SELECT 1 FROM cm.consents k2 JOIN cm.consents k"
    " ON k.consent_id = c.consent_id AND k2.person_id = k.person_id AND k2.source = k.source"
    " AND k2.purpose = k.purpose WHERE k2.state = 'withdrawn' AND k2.effective_at <= %(as_of)s"
    " AND k2.effective_at >= k.effective_at)))"
)


def _where(f: SearchFilter) -> tuple[str, dict[str, Any]]:
    w = ("c.patient_token = %(tok)s AND c.doc_type <> 'guideline' AND c.status <> 'withdrawn'"
         " AND c.recorded_at <= %(as_of)s AND (c.occurred_at IS NULL OR c.occurred_at <= %(as_of)s)"
         " AND c.sensitivity = ANY(%(sens)s)")
    p: dict[str, Any] = {"tok": f.patient_token, "as_of": f.as_of, "sens": list(f.sensitivities)}
    if f.doc_types:
        w += " AND c.doc_type = ANY(%(dts)s)"
        p["dts"] = list(f.doc_types)
    if f.date_from:
        w += " AND COALESCE(c.occurred_at, c.recorded_at) >= %(d0)s"
        p["d0"] = f.date_from
    if f.date_to:
        w += " AND COALESCE(c.occurred_at, c.recorded_at) <= %(d1)s"
        p["d1"] = f.date_to
    if f.consent:
        w += _CONSENT
    return w, p


def _check_token(tok: str) -> None:
    import re

    if not re.match(PATIENT_RE, tok or ""):
        raise ValueError("patient_token must look like P-0000 (no cross-patient or guideline search)")


def _vec_literal(v: Sequence[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def parse_vec(s: str | None) -> list[float] | None:
    return None if not s else [float(x) for x in s.strip("[]").split(",")]


def _vtype(conn: Any) -> str:
    r = conn.execute(
        "SELECT format_type(a.atttypid, a.atttypmod) AS t FROM pg_attribute a "
        "WHERE a.attrelid = 'cm.text_chunks'::regclass AND a.attname = 'embedding'"
    ).fetchone()
    return "halfvec" if r and str(r["t"]).startswith("halfvec") else "vector"


def fetch_pool(f: SearchFilter, *, limit: int = 2000, conn: Any = None) -> list[dict[str, Any]]:
    """All live chunks of the patient passing the prefilter (the lexical corpus). No embeddings."""
    _check_token(f.patient_token)
    if conn is None:
        with transaction() as c:
            return fetch_pool(f, limit=limit, conn=c)
    where, p = _where(f)
    p["lim"] = limit
    return list(conn.execute(
        f"SELECT {_COLS} FROM cm.text_chunks c WHERE {where} "  # noqa: S608 (fixed fragments, bound params)
        "ORDER BY COALESCE(c.occurred_at, c.recorded_at) DESC LIMIT %(lim)s", p).fetchall())


def vector_search(f: SearchFilter, qvec: Sequence[float], *, limit: int = 40,
                  conn: Any = None) -> list[dict[str, Any]]:
    """Exact cosine scan over the filtered rows. Adds `sim` (1 - distance) and `emb` (list of floats)."""
    _check_token(f.patient_token)
    if conn is None:
        with transaction() as c:
            return vector_search(f, qvec, limit=limit, conn=c)
    where, p = _where(f)
    vt = _vtype(conn)
    p.update(q=_vec_literal(qvec), lim=limit)
    rows = conn.execute(
        f"SELECT {_COLS}, 1 - (c.embedding <=> %(q)s::{vt}(1536)) AS sim, c.embedding::text AS emb_txt "  # noqa: S608
        f"FROM cm.text_chunks c WHERE {where} AND c.embedding IS NOT NULL "
        f"ORDER BY c.embedding <=> %(q)s::{vt}(1536) LIMIT %(lim)s", p).fetchall()
    out = []
    for r in rows:
        r = dict(r)
        r["emb"] = parse_vec(r.pop("emb_txt"))
        r["sim"] = float(r["sim"])
        out.append(r)
    return out


def fts_search(f: SearchFilter, query: str, *, limit: int = 40, conn: Any = None) -> list[dict[str, Any]]:
    """Fallback lexical leg: tsv @@ websearch_to_tsquery('simple'), ranked by ts_rank_cd (not BM25)."""
    _check_token(f.patient_token)
    if conn is None:
        with transaction() as c:
            return fts_search(f, query, limit=limit, conn=c)
    where, p = _where(f)
    p.update(q=query, lim=limit)
    return list(conn.execute(
        f"SELECT {_COLS}, ts_rank_cd(c.tsv, websearch_to_tsquery('simple', %(q)s)) AS rank "  # noqa: S608
        f"FROM cm.text_chunks c WHERE {where} AND c.tsv @@ websearch_to_tsquery('simple', %(q)s) "
        "ORDER BY rank DESC LIMIT %(lim)s", p).fetchall())


def fetch_embeddings(chunk_ids: Sequence[Any], f: SearchFilter, *, conn: Any = None) -> dict[Any, list[float]]:
    """Embeddings for given chunks, still passing the patient prefilter (used by MMR on BM25-only hits)."""
    _check_token(f.patient_token)
    if conn is None:
        with transaction() as c:
            return fetch_embeddings(chunk_ids, f, conn=c)
    where, p = _where(f)
    p["ids"] = list(chunk_ids)
    rows = conn.execute(
        f"SELECT c.chunk_id, c.embedding::text AS e FROM cm.text_chunks c WHERE {where} "  # noqa: S608
        "AND c.chunk_id = ANY(%(ids)s) AND c.embedding IS NOT NULL", p).fetchall()
    return {r["chunk_id"]: parse_vec(r["e"]) or [] for r in rows}
