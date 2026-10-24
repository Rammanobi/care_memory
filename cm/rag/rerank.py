"""Optional reranking. Default everywhere is rerank='none' (owner decision: no re-ranking for the hackathon).

'llm'   : WORKER model, one governed call over the top-20, strict JSON {"order": [1,3,...]}, capped output.
'cross' : local cross-encoder only if sentence-transformers and a model name (CM_RERANK_MODEL) are present;
          otherwise skipped with a clear note. No heavy dependency is added.
Both return (hits_in_new_order, note); on any failure the input order is kept and the note says why.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Any

TOP_IN = 20
MAX_TOKENS_NOTE = "output capped to a JSON list of at most TOP_IN integers"


def _snippet(t: str, n: int = 400) -> str:
    return " ".join(t.split())[:n]


def llm_rerank(query: str, hits: list[Any], *, model: Any = None, top_in: int = TOP_IN,
               patient_id: str | None = None) -> tuple[list[Any], str]:
    head, tail = hits[:top_in], hits[top_in:]
    if len(head) < 2:
        return hits, "llm rerank skipped: fewer than 2 candidates"
    try:
        from cm.core.tokenize import tokenize

        m = model or _worker()
        lines = "\n".join(f"{i + 1}. {_snippet(h.text)}" for i, h in enumerate(head))
        prompt = ("Rank the numbered passages by how well they answer the question. Reply with ONLY JSON: "
                  f'{{"order": [numbers, best first]}}. Use each number at most once.\n'
                  f"Question: {tokenize(query)}\nPassages:\n{lines}")
        out = m.invoke(prompt, task_id="rag-rerank", task_type="rerank", patient_id=patient_id,
                       max_tokens=3 * top_in + 20)
        order = parse_order(getattr(out, "content", out), len(head))
    except Exception as e:  # noqa: BLE001 - rerank must never break retrieval
        return hits, f"llm rerank skipped: {type(e).__name__}"
    if not order:
        return hits, "llm rerank skipped: unparseable JSON"
    seen = list(dict.fromkeys(order))
    seen += [i for i in range(1, len(head) + 1) if i not in seen]  # unlisted keep their relative order
    return [head[i - 1] for i in seen] + tail, "llm rerank applied"


def parse_order(raw: Any, n: int) -> list[int]:
    """Strict: JSON object with 'order' list of ints in 1..n (fences stripped). Anything else -> []."""
    s = re.sub(r"^```(?:json)?|```$", "", str(raw).strip(), flags=re.M).strip()
    try:
        d = json.loads(s)
        o = d["order"]
    except (ValueError, KeyError, TypeError):
        return []
    if not isinstance(o, list) or len(o) > n or not all(isinstance(i, int) and 1 <= i <= n for i in o):
        return []
    return o


def _worker() -> Any:
    from cm.core.llm import get_model

    return get_model("WORKER")


def cross_rerank(query: str, hits: list[Any], *, scorer: Callable[[list[tuple[str, str]]], list[float]] | None = None,
                 top_in: int = TOP_IN) -> tuple[list[Any], str]:
    head, tail = hits[:top_in], hits[top_in:]
    if scorer is None:
        name = os.environ.get("CM_RERANK_MODEL", "")
        if not name:
            return hits, "cross rerank skipped: CM_RERANK_MODEL not set"
        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            return hits, "cross rerank skipped: sentence-transformers is not installed"
        try:
            scorer = CrossEncoder(name).predict
        except Exception as e:  # noqa: BLE001
            return hits, f"cross rerank skipped: {type(e).__name__}"
    scores = list(scorer([(query, h.text) for h in head]))
    order = sorted(range(len(head)), key=lambda i: -float(scores[i]))
    return [head[i] for i in order] + tail, "cross rerank applied"
