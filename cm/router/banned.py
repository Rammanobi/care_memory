"""Lane F: banned-term check run before every patient or Supporter send (no TB, no disease or drug words)."""

from __future__ import annotations

import re

# Disease words (EN/HI/TE) and regimen drug names; substring match, case-insensitive.
_SUBSTRINGS = [
    "tuberculosis",
    "टीबी",
    "क्षय",
    "క్షయ",
    "rifampicin",
    "rifampin",
    "isoniazid",
    "pyrazinamide",
    "ethambutol",
    "streptomycin",
    "bedaquiline",
    "linezolid",
    "pretomanid",
    "moxifloxacin",
    "levofloxacin",
    "rifapentine",
    "cycloserine",
    "ethionamide",
    "delamanid",
    "clofazimine",
]
_SUB_RE = re.compile("|".join(re.escape(w) for w in _SUBSTRINGS), re.IGNORECASE)
# Short tokens only count as whole words.
_WHOLE_RE = re.compile(
    r"(?<![A-Za-z0-9])(dots|akt|hrze|fdc|t\.?\s?b\.?)(?![A-Za-z0-9])", re.IGNORECASE
)


def find_banned(text: str) -> list[str]:
    """Return the banned terms found in ``text`` (empty list means clean)."""
    found = {m.group(0).lower() for m in _SUB_RE.finditer(text)}
    for m in _WHOLE_RE.finditer(text):
        t = m.group(1).lower()
        found.add("tb" if t.replace(".", "").replace(" ", "") == "tb" else t)
    return sorted(found)


def is_clean(text: str) -> bool:
    return not find_banned(text)


class BannedTermError(ValueError):
    def __init__(self, terms: list[str]) -> None:
        super().__init__("banned terms: " + ", ".join(terms))
        self.terms = terms


def assert_clean(text: str) -> None:
    terms = find_banned(text)
    if terms:
        raise BannedTermError(terms)
