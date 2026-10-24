"""Banned-term filter and small-cell suppression."""

import pytest

from cm.api.suppress import clean_texts, find_banned, is_clean, suppress_small_cells


@pytest.mark.parametrize(
    "text", ["You have TB", "tuberculosis follow-up", "take Rifampicin daily", "HRZE course"]
)
def test_banned_terms_are_found(text: str) -> None:
    assert find_banned(text)
    assert not is_clean(text)


@pytest.mark.parametrize(
    "text", ["Please bring your medicine strip", "Visit on Wednesday", "tablet", "", None]
)
def test_clean_text_passes(text: str | None) -> None:
    assert is_clean(text)


def test_clean_texts_drops_items_with_banned_terms() -> None:
    items = [{"t": "hello"}, {"t": "your TB result"}, {"t": "see you"}]
    assert [i["t"] for i in clean_texts(items, ("t",))] == ["hello", "see you"]


def test_small_cells_are_hidden() -> None:
    rows = suppress_small_cells([{"n": 3}, {"n": 0}, {"n": 4}, {"n": 5}])
    assert [r["n"] for r in rows] == [None, 0, None, 5]
    assert [r["suppressed"] for r in rows] == [True, False, True, False]
