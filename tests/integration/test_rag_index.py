"""Patient RAG index against the caremem_test database only (the root conftest forces DB_NAME)."""

import hashlib
import struct
from datetime import timedelta

import pytest

from cm.core import clock
from cm.core.tokenize import assert_clean
from cm.rag.index import build_patient_index
from cm.store import chunks_repo

pytestmark = pytest.mark.usefixtures("pinned_clock")
TOKEN = "P-0142"


class FakeEmbedder:
    """Deterministic hash-based 1536-d vectors (offline)."""

    model = "fake-hash-1536"

    def __init__(self) -> None:
        self.calls = 0
        self.texts = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        self.texts += len(texts)
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest() * 48
            out.append([b / 255.0 - 0.5 for b in struct.unpack("1536B", h[:1536])])
        return out


@pytest.fixture()
def clean_index():
    chunks_repo.delete_patient_index(TOKEN)
    yield
    chunks_repo.delete_patient_index(TOKEN)


def test_build_idempotent_and_clean(clean_index):
    emb = FakeEmbedder()
    first = build_patient_index(TOKEN, clock.now(), embedder=emb)
    n = chunks_repo.count_chunks(TOKEN)
    assert first.chunks_total >= 1 and n == first.chunks_new > 0 and first.embedded > 0
    calls = emb.texts
    again = build_patient_index(TOKEN, clock.now(), embedder=emb)
    assert again.chunks_new == 0 and chunks_repo.count_chunks(TOKEN) == n
    assert emb.texts == calls  # nothing re-embedded
    rows = chunks_repo.list_chunks(TOKEN)
    for r in rows:
        assert_clean(r["content"])
        assert r["extra"]["kind"] in {"event", "window", "daily", "weekly"} | {"parent"}
        assert isinstance(r["extra"]["source_event_ids"], list)
        assert "bill" not in r["content"].lower()
    kinds = {r["extra"]["kind"] for r in rows}
    assert {"event", "daily"} <= kinds
    assert any(r["has_embedding"] for r in rows) and any(not r["has_embedding"] for r in rows)
    weekly = [r for r in rows if r["extra"]["kind"] == "weekly"]
    for r in weekly:
        assert "missed_7d" in r["extra"]["numbers"]
    assert chunks_repo.count_documents(TOKEN) >= len(rows)


def test_as_of_hides_future(clean_index):
    early = clock.now() - timedelta(days=20)
    build_patient_index(TOKEN, early)
    rows = chunks_repo.list_chunks(TOKEN)
    assert rows and all(r["occurred_at"] <= early and r["recorded_at"] <= early for r in rows)
    early_n = len(rows)
    build_patient_index(TOKEN, clock.now())
    assert chunks_repo.count_chunks(TOKEN) > early_n
    # an as_of-filtered read at the early time sees only the early chunks again
    assert len(chunks_repo.list_chunks(TOKEN, as_of=early)) == early_n


@pytest.mark.parametrize("strategy", ["fixed", "sentence", "event", "dynamic"])
def test_strategies_run(strategy, clean_index):
    s = build_patient_index(
        TOKEN, clock.now(), strategy=strategy, size=128, overlap=40, rollups=False
    )
    assert s.chunks_total > 0 and "daily" not in s.by_kind
