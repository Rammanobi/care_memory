"""Cite-or-cut: keep only sentences that carry a valid citation and state only known numbers.

A sentence is cut when it (a) has no citation, (b) cites an id that is not in the evidence, or
(c) contains a number that is not among the allowed feature numbers. The caller falls back to a template
card when nothing survives. Pure and deterministic; no LLM.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

_ID = r"[EBCRGD]-[0-9A-Za-z_]+"
CITE = re.compile(rf"\[({_ID})\]")  # single-ref form, kept for callers that import it
# Tolerant group form: [E-a, E-b] or [E-a; E-b]. A group starts with a ref-shaped id; every other item in it
# is returned as written, so a non-id item (e.g. "[E-a, see note]") fails the lookup and the sentence is cut.
CITE_GROUP = re.compile(rf"\[\s*({_ID}(?:\s*[,;]\s*[^\[\],;]+?)*)\s*\]")
_SPLIT = re.compile(r"\s*[,;]\s*")
_NUM = re.compile(r"(?<![\w-])\d+(?:\.\d+)?(?![\w-])")


@dataclass(frozen=True)
class Evidence:
    valid_ids: frozenset[str]
    numbers: frozenset[float]

    @classmethod
    def of(cls, ids: Iterable[str], numbers: Iterable[float]) -> Evidence:
        return cls(frozenset(ids), frozenset(float(n) for n in numbers))


@dataclass
class CutResult:
    kept: list[str] = field(default_factory=list)
    cut: list[tuple[str, str]] = field(default_factory=list)  # (sentence, reason)

    @property
    def all_cut(self) -> bool:
        return not self.kept

    @property
    def cut_ratio(self) -> float:
        total = len(self.kept) + len(self.cut)
        return len(self.cut) / total if total else 1.0


def refs_of(sentence: str) -> list[str]:
    """Every cited ref, in order. ``[E-a][E-b]`` and ``[E-a, E-b]`` both give ``["E-a", "E-b"]``."""
    return [r.strip() for g in CITE_GROUP.findall(sentence) for r in _SPLIT.split(g) if r.strip()]


def numbers_of(sentence: str) -> list[float]:
    """Numbers outside citation markers."""
    return [float(n) for n in _NUM.findall(CITE_GROUP.sub("", sentence))]


def check_sentence(sentence: str, evidence: Evidence) -> str | None:
    """Return a cut reason, or None when the sentence is fine."""
    refs = refs_of(sentence)
    if not refs:
        return "no_ref"
    if any(r not in evidence.valid_ids for r in refs):
        return "unknown_ref"
    if any(n not in evidence.numbers for n in numbers_of(sentence)):
        return "number_mismatch"
    return None


def cite_or_cut(draft: Iterable[str] | str, evidence: Evidence) -> CutResult:
    sentences = re.split(r"(?<=[.!?])\s+", draft.strip()) if isinstance(draft, str) else list(draft)
    out = CutResult()
    for s in (x.strip() for x in sentences if x.strip()):
        reason = check_sentence(s, evidence)
        (out.cut.append((s, reason)) if reason else out.kept.append(s))
    return out
