"""Banned-term scan for the narrator and other text guards (CLAUDE.md non-negotiable 5).

Thin wrapper over the shared lexicon ``cm/core/banned_lexicon.py``, the same source ``cm/router/banned.py``
uses, so the two guards cannot drift. Default audience is patient-strict (the narrator card may be forwarded);
pass ``audience="doctor"`` to allow disease words (drug names stay banned).
"""

from __future__ import annotations

from cm.core.banned_lexicon import DRUG_NAMES, find_banned  # noqa: F401  (DRUG_NAMES re-exported)


def find_banned_terms(text: str, lang: str = "en", audience: str = "patient") -> list[str]:
    """Every banned term found (empty list means clean). ``lang`` is accepted for the contract."""
    return find_banned(text, audience)
