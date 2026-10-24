"""Lane K (Content, mock feeds, RAG seed): chunking, rendering and indexing for the patient RAG index.

Modules owned by other agents (embed, retrieve, rerank) are imported by their own users, not here.
"""

from cm.rag.chunk import Chunk, chunk_messages, chunk_text, count_tokens
from cm.rag.index import Embedder, IndexStats, build_patient_index
from cm.rag.render import Rendered, RollupCard, build_rollup_cards, render_event

__all__ = [
    "Chunk",
    "Embedder",
    "IndexStats",
    "Rendered",
    "RollupCard",
    "build_patient_index",
    "build_rollup_cards",
    "chunk_messages",
    "chunk_text",
    "count_tokens",
    "render_event",
]
