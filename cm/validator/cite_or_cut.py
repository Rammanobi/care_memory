"""Cite-or-cut: keep only sentences that carry a valid citation and state only known numbers.

A sentence is cut when it (a) has no citation, (b) cites an id that is not in the evidence, or
(c) contains a number that is not among the allowed feature numbers. The caller falls back to a template
card when nothing survives. Pure and deterministic; no LLM.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

CITE = re.compile(r"\[([EBCRGD]-[0-9A-Za-z_]+)\]")
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
    return CITE.findall(sentence)


def numbers_of(sentence: str) -> list[float]:
    """Numbers outside citation markers."""
    return [float(n) for n in _NUM.findall(CITE.sub("", sentence))]


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
