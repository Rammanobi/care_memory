"""Single source of truth for banned terms (CLAUDE.md non-negotiable 5).

Two groups: DISEASE terms (TB, tuberculosis, DOTS, MDR/XDR, Telugu and Hindi disease words) and DRUG names
(first- and second-line regimen drugs). Patient- and Supporter-facing text must contain neither. Doctor-facing
text may mention disease terms but never drug names, so ``audience="doctor"`` skips the disease group only.
Both ``cm/router/banned.py`` (outbound) and ``cm/validator/banned_terms.py`` (narrator) delegate here.
"""

from __future__ import annotations

import re

DISEASE_SUBSTRINGS = ("tuberculosis", "टीबी", "क्षय", "టీబీ", "క్షయ")
DISEASE_WHOLE = ("dots", "mdr", "xdr", "tb")  # whole-word, case-insensitive; "tb" also matches T.B. / T B
DRUG_NAMES = (
    "isoniazid", "rifampicin", "rifampin", "pyrazinamide", "ethambutol", "streptomycin", "rifapentine",
    "bedaquiline", "linezolid", "pretomanid", "moxifloxacin", "levofloxacin", "cycloserine", "ethionamide",
    "delamanid", "clofazimine",
)
DRUG_WHOLE = ("akt", "hrze", "rhze", "fdc")

_DISEASE_SUB_RE = re.compile("|".join(re.escape(w) for w in DISEASE_SUBSTRINGS), re.IGNORECASE)
_DRUG_SUB_RE = re.compile("|".join(re.escape(w) for w in DRUG_NAMES), re.IGNORECASE)
_DISEASE_WHOLE_RE = re.compile(
    r"(?<![A-Za-z0-9])(dots|mdr|xdr|t\.?\s?b\.?)(?![A-Za-z0-9])", re.IGNORECASE
)
_DRUG_WHOLE_RE = re.compile(r"(?<![A-Za-z0-9])(akt|hrze|rhze|fdc)(?![A-Za-z0-9])", re.IGNORECASE)


def find_banned(text: str, audience: str = "patient") -> list[str]:
    """Banned terms in ``text``, lower-cased and sorted (empty means clean). ``audience``: patient | doctor."""
    found = {m.group(0).lower() for m in _DRUG_SUB_RE.finditer(text)}
    found |= {m.group(1).lower() for m in _DRUG_WHOLE_RE.finditer(text)}
    if audience != "doctor":
        found |= {m.group(0).lower() for m in _DISEASE_SUB_RE.finditer(text)}
        for m in _DISEASE_WHOLE_RE.finditer(text):
            t = m.group(1).lower()
            found.add("tb" if t.replace(".", "").replace(" ", "") == "tb" else t)
    return sorted(found)
