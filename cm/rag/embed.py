"""Embedder: governed OpenAI embeddings with batching, a content-hash cache and a dimension check.

The cache is a small sqlite file (CM_EMBED_CACHE, default .cache/embed_cache.sqlite) keyed by
sha256(model + normalised text), so re-embedding unchanged text costs nothing. Texts must already be
tokenized (no real PII); the governed model asserts that.
"""

from __future__ import annotations

import hashlib
import math
import os
import sqlite3
import struct
import threading
from collections.abc import Callable, Sequence
from typing import Any, Protocol

EMBED_DIM = 1536
BATCH_SIZE = 64


class EmbeddingDimError(ValueError):
    pass


def norm_text(text: str) -> str:
    return " ".join(text.split())


def text_key(model: str, text: str) -> str:
    return hashlib.sha256((model + "\x00" + norm_text(text)).encode("utf-8")).hexdigest()


class Embedding(Protocol):
    model: str

    def embed_documents(self, texts: Sequence[str], **kw: Any) -> list[list[float]]: ...
    def embed_query(self, text: str, **kw: Any) -> list[float]: ...


def check_dim(vec: Sequence[float], dim: int = EMBED_DIM) -> None:
    if len(vec) != dim:
        raise EmbeddingDimError(f"embedding has {len(vec)} dims, halfvec column needs {dim}")


class _Cache:
    def __init__(self, path: str | None) -> None:
        self._mem: dict[str, bytes] = {}
        self._db: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        if path:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            self._db = sqlite3.connect(path, check_same_thread=False)
            self._db.execute("CREATE TABLE IF NOT EXISTS emb (k TEXT PRIMARY KEY, v BLOB NOT NULL)")

    def get(self, k: str) -> list[float] | None:
        with self._lock:
            b = self._mem.get(k)
            if b is None and self._db is not None:
                row = self._db.execute("SELECT v FROM emb WHERE k=?", (k,)).fetchone()
                b = row[0] if row else None
            if b is None:
                return None
            return list(struct.unpack(f"{len(b) // 4}f", b))

    def put(self, k: str, v: Sequence[float]) -> None:
        b = struct.pack(f"{len(v)}f", *v)
        with self._lock:
            self._mem[k] = b
            if self._db is not None:
                self._db.execute("INSERT OR REPLACE INTO emb (k, v) VALUES (?, ?)", (k, b))
                self._db.commit()


class Embedder:
    """Cached, batched, dimension-checked wrapper over get_model('EMBEDDING')."""

    def __init__(self, model: Any = None, *, model_name: str | None = None, cache_path: str | None = "",
                 batch_size: int = BATCH_SIZE, dim: int = EMBED_DIM,
                 task_type: str = "embed") -> None:
        self._model = model
        self.model = model_name or os.environ.get("EMBEDDING_MODEL", "openai:text-embedding-3-small")
        self.batch_size, self.dim, self.task_type = batch_size, dim, task_type
        path = os.environ.get("CM_EMBED_CACHE", ".cache/embed_cache.sqlite") if cache_path == "" else cache_path
        self._cache = _Cache(path or None)
        self.api_calls = 0  # texts sent to the provider (cache misses), for tests and cost reports

    def _m(self) -> Any:
        if self._model is None:
            from cm.core.llm import get_model

            self._model = get_model("EMBEDDING")
        return self._model

    def embed_documents(self, texts: Sequence[str], *, task_id: str = "embed",
                        patient_id: str | None = None) -> list[list[float]]:
        keys = [text_key(self.model, t) for t in texts]
        out: dict[str, list[float]] = {}
        misses: dict[str, str] = {}
        for k, t in zip(keys, texts, strict=True):
            hit = self._cache.get(k)
            if hit is not None and len(hit) == self.dim:
                out[k] = hit
            else:
                misses[k] = norm_text(t)
        items = list(misses.items())
        for i in range(0, len(items), self.batch_size):
            part = items[i : i + self.batch_size]
            vecs = self._m().embed_documents([t for _, t in part], task_id=task_id,
                                             task_type=self.task_type, patient_id=patient_id)
            if len(vecs) != len(part):
                raise EmbeddingDimError("provider returned a different number of vectors")
            self.api_calls += len(part)
            for (k, _), v in zip(part, vecs, strict=True):
                check_dim(v, self.dim)
                self._cache.put(k, v)
                out[k] = list(v)
        return [out[k] for k in keys]

    def embed_query(self, text: str, *, task_id: str = "embed-q", patient_id: str | None = None) -> list[float]:
        return self.embed_documents([text], task_id=task_id, patient_id=patient_id)[0]


class FakeEmbedder:
    """Deterministic, offline: hashed bag-of-words into `dim` buckets, L2-normalised. Similar text -> close."""

    model = "fake:hash-bow"

    def __init__(self, dim: int = EMBED_DIM) -> None:
        self.dim = dim
        self.api_calls = 0

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in norm_text(text).lower().split():
            h = int.from_bytes(hashlib.sha256(tok.encode()).digest()[:8], "big")
            v[h % self.dim] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts: Sequence[str], **_: Any) -> list[list[float]]:
        self.api_calls += len(texts)
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str, **_: Any) -> list[float]:
        return self._vec(text)


def get_embedder(factory: Callable[[], Embedding] | None = None) -> Embedding:
    """The real cached Embedder, or whatever the factory returns (tests pass FakeEmbedder)."""
    if factory:
        return factory()
    return Embedder()
