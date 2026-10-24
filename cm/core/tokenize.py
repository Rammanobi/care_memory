"""PII tokenizer and guard (04_platform F6). Deterministic placeholders; no PII in logs or errors."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    # Indian mobile: optional +91 / 91 / 0 prefix, any single space/hyphen grouping (5-5, 3-3-4, 4-3-3 ...).
    ("PHONE", re.compile(r"(?<![\w-])(?:(?:\+?91|0)[\s-]?)?[6-9](?:[\s-]?\d){9}(?!\w)")),
    # Aadhaar: 12 digits, grouped 4-4-4 by spaces or hyphens, or unbroken.
    ("AADHAAR", re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")),
    ("ID", re.compile(r"\b(?:NIK|NI|PAT|MRN)[-\s]?\d{4,}\b", re.I)),
    ("NAME", re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Shri|Smt|Sri)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?")),
]
_TOKEN = re.compile(r"\[[A-Z]+_\d+\]")
_known_names: set[str] = set()


class PIILeak(ValueError):
    """Raised by assert_clean. Message names only the category, never the value."""

    error_class = "invalid"


def register_names(names: Iterable[str]) -> None:
    """Known patient/supporter names to scrub (from the request's own context)."""
    _known_names.update(n.strip() for n in names if len(n.strip()) >= 3)


def clear_names() -> None:
    _known_names.clear()


def tokenize(text: str, names: Iterable[str] = ()) -> str:
    """Replace PII with stable tokens like [PHONE_1]; same value gives the same token within a call."""
    seen: dict[str, str] = {}
    counts: dict[str, int] = {}

    def sub(label: str) -> Callable[[re.Match[str]], str]:
        def fn(m: re.Match[str]) -> str:
            v = m.group(0)
            if v not in seen:
                counts[label] = counts.get(label, 0) + 1
                seen[v] = f"[{label}_{counts[label]}]"
            return seen[v]

        return fn

    out = text
    for n in sorted(_known_names | {x for x in names if x}, key=len, reverse=True):
        out = re.sub(re.escape(n), sub("NAME"), out, flags=re.I)
    for label, pat in _PATTERNS:
        out = pat.sub(sub(label), out)
    return out


def assert_clean(text: str, names: Iterable[str] = ()) -> None:
    """Raise PIILeak if raw PII remains. Placeholders are fine."""
    probe = _TOKEN.sub("", text)
    for label, pat in _PATTERNS:
        if pat.search(probe):
            raise PIILeak(f"raw {label.lower()} in prompt")
    for n in _known_names | {x for x in names if x}:
        if re.search(re.escape(n), probe, flags=re.I):
            raise PIILeak("known name in prompt")
