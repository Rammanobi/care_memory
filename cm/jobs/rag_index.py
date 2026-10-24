"""(Re)index patient memory for RAG.

    python -m cm.jobs.rag_index --patient PT-0142 [--as-of 2026-02-10T09:00:00+00:00] [--no-embed]
    python -m cm.jobs.rag_index --all --nightly            # memory nightly, then index every patient

Idempotent: ``cm.rag.index.build_patient_index`` upserts on content hashes, so re-running adds nothing and
re-embeds nothing. ``index_after_nightly`` is the hook the nightly job calls once ``cm.memory`` has finished.
This job writes to whichever database ``DB_NAME`` points at; tests only ever use ``caremem_test``.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

from cm.core import clock
from cm.core.logging import get_logger
from cm.rag.index import IndexStats, build_patient_index

log = get_logger()


class EmbedAdapter:
    """Adapts anything with ``embed_documents`` (the cached governed Embedder, FakeEmbedder) to ``embed``."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.model = getattr(inner, "model", type(inner).__name__)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._inner.embed_documents(texts, task_id="rag-index")


def _real_embedder() -> Any | None:
    """The governed OpenAI embedder when a key is present, else None (chunks stay full-text only)."""
    import os

    if not os.environ.get("OPENAI_API_KEY"):
        return None
    from cm.core.budget_pg import install_governor
    from cm.rag.embed import Embedder

    install_governor()
    return EmbedAdapter(Embedder())


def index_patient(
    code: str, as_of: datetime | None = None, *, embedder: Any = None, embed: bool = True, conn: Any = None
) -> IndexStats:
    """Index one patient (PT-0142 or P-0142) at ``as_of`` (default: the pinned/sim clock)."""
    from cm.tools.memory_search import token_of

    token = token_of(code)
    if embedder is not None and not hasattr(embedder, "embed"):
        embedder = EmbedAdapter(embedder)
    if embedder is None and embed:
        embedder = _real_embedder()
    return build_patient_index(token, as_of or clock.now(), embedder=embedder, conn=conn)


def index_after_nightly(
    as_of: datetime | None = None, codes: list[str] | None = None, *, embedder: Any = None, embed: bool = True
) -> dict[str, Any]:
    """Nightly hook: call after ``cm.memory.nightly.run_nightly``. One failing patient never blocks the rest."""
    at = as_of or clock.now()
    if codes is None:
        from cm.api import (
            readmodels as rm,  # read-only patient list (no store helper lists tokens yet)
        )
        from cm.core.db import transaction

        with transaction() as conn:
            codes = sorted(p.code for p in rm.ui_patients(conn, at))
    out: dict[str, Any] = {"patients": len(codes), "chunks_new": 0, "embedded": 0, "failed": []}
    for c in codes:
        try:
            s = index_patient(c, at, embedder=embedder, embed=embed)
            out["chunks_new"] += s.chunks_new
            out["embedded"] += s.embedded
        except Exception as e:  # noqa: BLE001
            log.warning("rag_index_failed", patient=c, reason=type(e).__name__)
            out["failed"].append(c)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--patient")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--as-of", help="ISO timestamp; default is the pinned/sim clock")
    ap.add_argument("--no-embed", action="store_true", help="full-text only, no embedding calls")
    ap.add_argument("--nightly", action="store_true", help="run the memory nightly pipeline first (--all)")
    a = ap.parse_args()
    from cm.core.config import load_dotenv
    from cm.core.db import transaction

    load_dotenv()
    with transaction() as conn:
        clock.load_pin(conn)
    at = datetime.fromisoformat(a.as_of) if a.as_of else clock.now()
    if a.nightly:
        from cm.memory.nightly import run_nightly

        print(json.dumps({"nightly": run_nightly(at)}))
    if a.patient:
        s = index_patient(a.patient, at, embed=not a.no_embed)
        print(json.dumps({"patient": s.patient_token, "chunks_total": s.chunks_total, "chunks_new": s.chunks_new,
                          "embedded": s.embedded, "by_kind": s.by_kind}))
    else:
        print(json.dumps(index_after_nightly(at, embed=not a.no_embed)))


if __name__ == "__main__":
    main()
