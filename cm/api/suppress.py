"""Lane B: output suppression.

* Banned-term filter: patient and Supporter responses must never contain "TB", "tuberculosis" or
  drug names (non-negotiable 5).
* Small-cell suppression for officer-facing counts (1 <= n <= 4 is hidden).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from cm.router.banned import find_banned as _router_banned

SMALL_CELL_THRESHOLD = 5  # counts 1..THRESHOLD-1 are hidden in officer-facing views
SMALL_CELL_MAX = SMALL_CELL_THRESHOLD - 1

BANNED_TERMS: tuple[str, ...] = (
    "tb",
    "tuberculosis",
    "mdr",
    "xdr",
    "dots",
    "isoniazid",
    "rifampicin",
    "rifampin",
    "ethambutol",
    "pyrazinamide",
    "streptomycin",
    "bedaquiline",
    "linezolid",
    "delamanid",
    "pretomanid",
    "rifapentine",
    "moxifloxacin",
    "levofloxacin",
    "cycloserine",
    "clofazimine",
    "hrze",
    "rhze",
)
_BANNED_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in BANNED_TERMS) + r")\b", re.IGNORECASE
)


def find_banned(text: str | None) -> list[str]:
    """Banned terms present in `text` (lower-case, de-duplicated, in order of appearance)."""
    if not text:
        return []
    seen: list[str] = []
    for m in _BANNED_RE.finditer(text):
        t = m.group(1).lower()
        if t not in seen:
            seen.append(t)
    for t in _router_banned(text):  # one list of words for the gate, the portal and the sender
        t = t.lower()
        if t not in seen:
            seen.append(t)
    return seen


def is_clean(text: str | None) -> bool:
    return not find_banned(text)


def clean_texts(items: Iterable[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    """Drop every item whose listed text fields contain a banned term (withheld, never rewritten)."""
    return [it for it in items if all(is_clean(str(it.get(f) or "")) for f in fields)]


def suppress_small_cells(rows: Iterable[dict[str, Any]], key: str = "n") -> list[dict[str, Any]]:
    """Officer-facing counts: replace 1..4 with a suppressed marker."""
    out = []
    for r in rows:
        n = r.get(key)
        hidden = isinstance(n, int) and 1 <= n <= SMALL_CELL_MAX
        out.append({**r, key: None if hidden else n, "suppressed": hidden})
    return out
