"""Lane K: deterministic text chunking for the patient RAG index (RAG_STRATEGY_v2.md section 2). No LLM.

Strategies: ``fixed`` (token windows with overlap), ``sentence`` (sentences packed to a size, overlap by
sentences), ``event`` (one chunk per call) and ``dynamic`` (short text whole, long text in sentence-aware
windows under parent chunks; conversations via ``chunk_messages``).

Token counting uses tiktoken ``cl100k_base`` when it is installed and its vocabulary is available. Otherwise a
documented fallback counts one token per whitespace-delimited word (Telugu is space separated, so this stays
roughly proportional). Windows only ever cut on character boundaries, so Telugu (multi-byte) text is never split
inside a character.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

STRATEGIES = ("fixed", "sentence", "event", "dynamic")
DEFAULT_SIZE = 256
DEFAULT_OVERLAP = 100
PARENT_CAP_TOKENS = 1500
CONVERSATION_WINDOW = 6
CONVERSATION_OVERLAP = 2
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?।॥])\s+|\n+")  # includes the danda used in Indic text


@dataclass(frozen=True)
class Chunk:
    """One chunk. ``parent_seq`` points at the ``seq`` of a parent chunk in the same result list."""

    text: str
    tokens: int
    seq: int
    parent_seq: int | None = None
    role: str = "chunk"  # "chunk" (searchable) or "parent" (context only)


@lru_cache(maxsize=1)
def _encoder() -> Any | None:
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception:  # not installed, or vocabulary not cached and offline
        return None


def tokenizer_name() -> str:
    return "tiktoken:cl100k_base" if _encoder() is not None else "words"


def count_tokens(text: str) -> int:
    enc = _encoder()
    if enc is not None:
        return len(enc.encode(text, disallowed_special=()))
    return len(text.split())


def _units(text: str) -> list[tuple[str, int]]:
    """Split text into (piece, token_count) units whose concatenation is exactly the text.

    A unit never ends inside a UTF-8 character: tokens that start with a continuation byte are merged into the
    previous unit.
    """
    enc = _encoder()
    if enc is None:
        return [(m, 1 if m.strip() else 0) for m in re.findall(r"\S+\s*|\s+", text)]
    toks = enc.decode_tokens_bytes(enc.encode(text, disallowed_special=()))
    out: list[tuple[str, int]] = []
    cur = bytearray()
    n = 0
    for b in toks:
        if cur and (b[0] & 0xC0) != 0x80:
            out.append((cur.decode("utf-8", errors="replace"), n))
            cur, n = bytearray(), 0
        cur += b
        n += 1
    if cur:
        out.append((cur.decode("utf-8", errors="replace"), n))
    return out


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s and s.strip()]


def _fixed(text: str, size: int, overlap: int) -> list[str]:
    units = _units(text)
    n = len(units)
    if sum(c for _, c in units) <= size:
        return [text.strip()] if text.strip() else []
    out: list[str] = []
    start = 0
    while start < n:
        end, tot = start, 0
        while end < n and (end == start or tot + units[end][1] <= size):
            tot += units[end][1]
            end += 1
        piece = "".join(u for u, _ in units[start:end]).strip()
        if piece:
            out.append(piece)
        if end >= n:
            break
        back, acc = end, 0
        while back > start + 1 and acc + units[back - 1][1] <= overlap:
            acc += units[back - 1][1]
            back -= 1
        start = max(back, start + 1)
    return out


def _sentence_chunks(sents: list[str], size: int, overlap: int) -> list[str]:
    out: list[str] = []
    cur: list[tuple[str, int]] = []
    fresh = 0  # sentences in cur that are not just carried-over overlap
    tot = 0
    for s in sents:
        n = count_tokens(s)
        if n > size:  # one huge sentence: window it on its own
            if fresh:
                out.append(" ".join(x for x, _ in cur))
            cur, fresh, tot = [], 0, 0
            out.extend(_fixed(s, size, overlap))
            continue
        if cur and tot + n > size and fresh:
            out.append(" ".join(x for x, _ in cur))
            tail: list[tuple[str, int]] = []
            acc = 0
            for x, xn in reversed(cur):
                if acc + xn > overlap or acc + xn + n > size:
                    break
                tail.insert(0, (x, xn))
                acc += xn
            cur, tot, fresh = tail, acc, 0
        cur.append((s, n))
        tot += n
        fresh += 1
    if fresh:
        out.append(" ".join(x for x, _ in cur))
    return out


def _mk(
    texts: list[str], parent_seq: int | None = None, start: int = 0, role: str = "chunk"
) -> list[Chunk]:
    return [Chunk(t, count_tokens(t), start + i, parent_seq, role) for i, t in enumerate(texts)]


def _dynamic(text: str, size: int, overlap: int) -> list[Chunk]:
    if count_tokens(text) <= size:
        return _mk([text])
    parents = _sentence_chunks(split_sentences(text), PARENT_CAP_TOKENS, 0)
    out: list[Chunk] = []
    for ptxt in parents:
        kids = _sentence_chunks(split_sentences(ptxt), size, overlap)
        pseq = len(out)
        out.append(Chunk(ptxt, count_tokens(ptxt), pseq, None, "parent"))
        out.extend(_mk(kids, parent_seq=pseq, start=len(out)))
    return out


def chunk_text(
    text: str,
    *,
    size_tokens: int = DEFAULT_SIZE,
    overlap_tokens: int = DEFAULT_OVERLAP,
    strategy: str = "dynamic",
) -> list[Chunk]:
    """Chunk one source text. Deterministic; same input and arguments always give the same list."""
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown chunk strategy {strategy!r}; expected one of {STRATEGIES}")
    if size_tokens < 1 or overlap_tokens < 0:
        raise ValueError("size_tokens must be >= 1 and overlap_tokens >= 0")
    text = (text or "").strip()
    if not text:
        return []
    if strategy == "event":
        return _mk([text])
    if overlap_tokens >= size_tokens:
        raise ValueError("overlap_tokens must be smaller than size_tokens")
    if strategy == "fixed":
        return _mk(_fixed(text, size_tokens, overlap_tokens))
    if strategy == "sentence":
        return _mk(_sentence_chunks(split_sentences(text), size_tokens, overlap_tokens))
    return _dynamic(text, size_tokens, overlap_tokens)


def message_windows(
    messages: list[str],
    *,
    window: int = CONVERSATION_WINDOW,
    overlap: int = CONVERSATION_OVERLAP,
    size_tokens: int = DEFAULT_SIZE,
) -> list[tuple[int, int]]:
    """Index spans [i, j) of sliding windows of ``window`` messages with ``overlap`` shared messages.

    A window longer than ``size_tokens`` is shortened from the end (fewer messages) but never below one message.
    Blank messages are not removed here; callers pass clean messages.
    """
    if window < 1 or not 0 <= overlap < window:
        raise ValueError("need window >= 1 and 0 <= overlap < window")
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(messages):
        j = min(i + window, len(messages))
        while j - i > 1 and count_tokens("\n".join(messages[i:j])) > size_tokens:
            j -= 1
        spans.append((i, j))
        if j >= len(messages):
            break
        i = max(j - overlap, i + 1)
    return spans


def chunk_messages(
    messages: list[str],
    *,
    window: int = CONVERSATION_WINDOW,
    overlap: int = CONVERSATION_OVERLAP,
    size_tokens: int = DEFAULT_SIZE,
) -> list[Chunk]:
    """One chunk per sliding window of consecutive messages (see ``message_windows``)."""
    msgs = [m.strip() for m in messages if m and m.strip()]
    out: list[Chunk] = []
    for i, j in message_windows(msgs, window=window, overlap=overlap, size_tokens=size_tokens):
        text = "\n".join(msgs[i:j])
        out.append(Chunk(text, count_tokens(text), len(out)))
    return out
