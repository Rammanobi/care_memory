"""Banned-term scan for patient- and Supporter-facing text (CLAUDE.md non-negotiable 5).

Same term list as scripts/banned_terms.py (kept in sync by tests/unit/ai/test_validator.py).
"""

import re

DRUG_NAMES = ("isoniazid", "rifampicin", "rifampin", "pyrazinamide", "ethambutol", "streptomycin",
              "rifapentine", "bedaquiline", "linezolid")
_CI = re.compile(r"\b(tuberculosis|" + "|".join(DRUG_NAMES) + r")\b", re.IGNORECASE)
_UPPER = re.compile(r"\b(TB|DOTS)\b")
_NON_LATIN = ("टीबी", "क्षय", "క్షయ", "టీబీ")


def find_banned_terms(text: str, lang: str = "en") -> list[str]:
    """Return every banned term found (empty list means clean). ``lang`` is accepted for the contract."""
    hits = [m.group(0) for m in _CI.finditer(text)] + [m.group(0) for m in _UPPER.finditer(text)]
    hits += [t for t in _NON_LATIN if t in text]
    return hits
