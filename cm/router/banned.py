"""Lane F: banned-term check run before every patient or Supporter send (no TB, no disease or drug words)."""

from __future__ import annotations

from cm.core.banned_lexicon import find_banned as _find


def find_banned(text: str) -> list[str]:
    """Return the banned terms found in ``text`` (empty list means clean). Patient-facing: strict."""
    return _find(text, "patient")


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
