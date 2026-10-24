"""Vault name decrypt for reminders: first name only, safe, no other field."""

from __future__ import annotations

import pytest

from cm.store.channels_repo import first_name_from_vault


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        (b"Ravi", "Ravi"),
        (memoryview(b"Lakshmi Devi"), "Lakshmi"),
        (b"Dr. Anil Rao", "Anil"),
        ("రవి".encode(), "రవి"),
        (None, None),
        (b"", None),
        (b"\xff\xfe", None),
        (b"1234", None),
    ],
)
def test_first_name_from_vault(raw: object, want: str | None) -> None:
    assert first_name_from_vault(raw) == want


def test_first_name_never_returns_more_than_a_word() -> None:
    assert first_name_from_vault(b"Ravi\nphone 9999999999") == "Ravi"
