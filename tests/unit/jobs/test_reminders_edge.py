"""Edge cases for the daily reminder producer. Repo and DB calls are faked: nothing touches a database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from cm.jobs import reminders
from cm.router.banned import find_banned
from cm.router.quiet_hours import IST


def ist(h: int, m: int = 0, s: int = 0) -> datetime:
    return datetime(2026, 3, 2, h, m, s, tzinfo=IST).astimezone(UTC)


class Tx:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, *a: object) -> None:
        return None


@pytest.fixture()
def world(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DEMO_IGNORE_QUIET_HOURS", raising=False)  # dev .env override must not leak in
    class W:
        rows: list[dict[str, Any]] = []
        targets: list[dict[str, Any]] = []
        consent: dict[Any, bool] = {}
        template_ok = True
        seen_keys: set[str] = set()

    w = W()
    w.rows, w.targets, w.consent, w.seen_keys = [], [], {}, set()
    monkeypatch.setattr(reminders.channels_repo, "reminder_targets", lambda: w.targets)
    monkeypatch.setattr(reminders.channels_repo, "ensure_template", lambda *a, **k: uuid4() if w.template_ok else None)
    monkeypatch.setattr(reminders.db, "transaction", lambda: Tx())

    def enq(row: dict[str, Any], conn: object = None) -> Any:
        if row["dedup_key"] in w.seen_keys:
            return uuid4()  # existing row won: a different id comes back
        w.seen_keys.add(row["dedup_key"])
        w.rows.append(row)
        return row["outbox_id"]

    monkeypatch.setattr(reminders.outbox_repo, "enqueue", enq)
    monkeypatch.setattr(reminders.PgConsents, "has_consent", lambda self, pid, *a: w.consent.get(pid, True))
    return w


def target(name: str | None = "Ravi", lang: str = "en") -> dict[str, Any]:
    return {"person_id": uuid4(), "patient_id": uuid4(), "lang": lang, "first_name": name}


def test_no_targets_creates_nothing(world) -> None:
    assert reminders.produce(ist(9)) == {"created": 0, "existing": 0, "no_consent": 0, "no_template": 0}


def test_no_consent_patient_skipped(world) -> None:
    t = target()
    world.targets.append(t)
    world.consent[t["person_id"]] = False  # e.g. /stop was typed
    out = reminders.produce(ist(9))
    assert out["no_consent"] == 1 and out["created"] == 0 and world.rows == []


def test_rerun_same_day_is_idempotent(world) -> None:
    world.targets.append(target())
    assert reminders.produce(ist(9))["created"] == 1
    out = reminders.produce(ist(9, 30))
    assert out["created"] == 0 and out["existing"] == 1 and len(world.rows) == 1


def test_next_day_creates_a_new_row(world) -> None:
    world.targets.append(target())
    reminders.produce(ist(9))
    out = reminders.produce(ist(9) + timedelta(days=1))
    assert out["created"] == 1 and len(world.rows) == 2


def test_ist_date_used_for_dedup_not_utc(world) -> None:
    world.targets.append(target())
    # 00:30 IST on Mar 2 is 19:00 UTC on Mar 1: the IST day is Mar 2
    reminders.produce(ist(0, 30))
    assert str(world.rows[0]["for_date"]) == "2026-03-02"
    assert world.rows[0]["dedup_key"].endswith("2026-03-02")


@pytest.mark.parametrize(
    ("at", "deferred"),
    [(ist(20, 59, 59), False), (ist(21, 0), True), (ist(23, 0), True), (ist(6, 59, 59), True), (ist(7, 0), False)],
)
def test_quiet_hours_boundaries_schedule_next_open(world, at: datetime, deferred: bool) -> None:
    world.targets.append(target())
    reminders.produce(at)
    nxt = world.rows[0]["next_attempt_at"]
    if deferred:
        assert nxt > at and nxt.astimezone(IST).hour == 7 and nxt.astimezone(IST).minute == 0
    else:
        assert nxt == at


def test_late_night_rolls_to_next_morning(world) -> None:
    world.targets.append(target())
    reminders.produce(ist(21, 0))
    assert world.rows[0]["next_attempt_at"] == ist(7, 0) + timedelta(days=1)


def test_missing_template_counted_not_raised(world) -> None:
    world.targets.append(target())
    world.template_ok = False
    out = reminders.produce(ist(9))
    assert out["no_template"] == 1 and world.rows == []


@pytest.mark.parametrize("lang", ["te", "hi", "xx", "", "EN", None])
def test_unknown_or_missing_language_falls_back_and_stays_clean(world, lang) -> None:
    world.targets.append(target(lang=lang))
    assert reminders.produce(ist(9))["created"] == 1
    assert not find_banned(world.rows[0]["body"])


@pytest.mark.parametrize("name", ["రవి", "Ravi" * 500, "  ", "O'Brien <b>", "Dots", "టీబీ", "T.B."])
def test_odd_names_never_leave_banned_text_or_placeholder(world, name: str) -> None:
    world.targets.append(target(name=name))
    reminders.produce(ist(9))
    body = world.rows[0]["body"]
    assert not find_banned(body)
    assert "{first_name}" not in body


def test_banned_names_fall_back_to_friend(world) -> None:
    for n in ["Dots", "టీబీ", "T.B.", "Rifampicin"]:
        assert reminders.greeting_name(n) == "friend"


def test_every_row_has_dose_buttons_and_telegram_channel(world) -> None:
    world.targets.extend([target(), target("Sita")])
    reminders.produce(ist(9))
    for r in world.rows:
        assert r["channel"] == "telegram" and r["kind"] == "checkin"
        kb = r["meta"]["reply_markup"]["inline_keyboard"][0]
        assert [b["callback_data"].split(":")[2] for b in kb] == ["t", "m", "u"]
        assert all(r["outbox_id"].hex in b["callback_data"] for b in kb)


def test_unapproved_or_unknown_template_raises() -> None:
    with pytest.raises(KeyError):
        reminders.load_template("does_not_exist")
