"""Reminder greeting: decrypted first name, neutral fallback, nothing banned reaches the patient."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from cm.jobs import reminders
from cm.router.banned import find_banned


def test_greeting_name_uses_name_or_falls_back() -> None:
    assert reminders.greeting_name("Ravi") == "Ravi"
    assert reminders.greeting_name(None) == "friend"
    assert reminders.greeting_name("") == "friend"


def test_greeting_name_never_passes_a_banned_term() -> None:
    assert reminders.greeting_name("Tuberculosis") == "friend"
    assert reminders.greeting_name("Rifampicin") == "friend"


def test_template_has_no_banned_terms_for_any_language() -> None:
    tpl = reminders.load_template()
    for lang in tpl["languages"].values():
        assert not find_banned(lang["telegram"].replace("{first_name}", "Ravi"))


@pytest.mark.parametrize(("name", "expect"), [("Ravi", "Ravi"), (None, "friend")])
def test_produce_renders_the_name(monkeypatch: pytest.MonkeyPatch, name: str | None, expect: str) -> None:
    seen: list[dict[str, Any]] = []
    pid = uuid4()

    class Tx:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(
        reminders.channels_repo,
        "reminder_targets",
        lambda: [{"person_id": pid, "patient_id": uuid4(), "lang": "en", "first_name": name}],
    )
    monkeypatch.setattr(reminders.channels_repo, "ensure_template", lambda *a, **k: uuid4())
    monkeypatch.setattr(reminders.db, "transaction", lambda: Tx())
    monkeypatch.setattr(reminders.outbox_repo, "enqueue", lambda row, conn=None: (seen.append(row), row["outbox_id"])[1])
    monkeypatch.setattr(reminders.PgConsents, "has_consent", lambda self, *a: True)
    out = reminders.produce(datetime(2026, 3, 2, 8, 0, tzinfo=UTC))
    assert out["created"] == 1
    body = seen[0]["body"]
    assert expect in body and "{first_name}" not in body
    assert not find_banned(body)
    assert set(seen[0]["meta"]) == {"reply_markup", "template"}
