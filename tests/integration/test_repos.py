"""Store repos against the compose database."""

from datetime import timedelta
from typing import Any
from uuid import uuid4

import psycopg
import pytest

from cm.core import clock
from cm.core.db import transaction
from cm.store import consent as consent_repo
from cm.store import events_repo, outbox_repo, settings_repo
from cm.store.events_repo import NewEvent

pytestmark = pytest.mark.db


def _event(actors: dict[str, Any], key: str, occurred: Any, recorded: Any) -> NewEvent:
    return NewEvent(
        patient_id=actors["patient_id"],
        type="ContextNote",
        occurred_at=occurred,
        recorded_at=recorded,
        source="system",
        payload={"text": key},
        idempotency_key=key,
    )


def test_append_is_idempotent_on_key(actors: dict[str, Any]) -> None:
    now = clock.now()
    key = f"test:{uuid4()}"
    first, created1 = events_repo.append_event(_event(actors, key, now, now))
    second, created2 = events_repo.append_event(_event(actors, key, now, now))
    assert created1 and not created2 and first == second


def test_bulk_append_counts_only_new(actors: dict[str, Any]) -> None:
    now = clock.now()
    batch = [_event(actors, f"test:{uuid4()}", now, now) for _ in range(3)]
    assert events_repo.bulk_append(batch) == 3
    assert events_repo.bulk_append(batch) == 0


def test_query_respects_occurred_and_recorded_as_of(actors: dict[str, Any]) -> None:
    now = clock.now()
    key = f"test:{uuid4()}"
    occurred, recorded = now - timedelta(days=2), now - timedelta(days=1)
    events_repo.append_event(_event(actors, key, occurred, recorded))

    def keys(as_of: Any, rec: Any = None) -> set[str]:
        return {e["idempotency_key"] for e in events_repo.query(actors["patient_id"], as_of, rec)}

    assert key not in keys(occurred - timedelta(hours=1))  # before it happened
    assert key not in keys(now, occurred + timedelta(hours=1))  # happened, not yet recorded
    assert key in keys(now)  # both known
    assert key in keys(recorded + timedelta(minutes=1))


def test_events_are_append_only(actors: dict[str, Any]) -> None:
    now = clock.now()
    eid, _ = events_repo.append_event(_event(actors, f"test:{uuid4()}", now, now))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), transaction() as conn:
        conn.execute("UPDATE cm.events SET payload='{}' WHERE event_id=%s", (eid,))


def test_outbox_refuses_rows_without_approval(actors: dict[str, Any]) -> None:
    row = {
        "kind": "ai_message",
        "recipient_id": actors["patient_person"],
        "channel": "telegram",
        "body": "hi",
        "next_attempt_at": clock.now(),
        "dedup_key": f"test:{uuid4()}",
    }
    with pytest.raises(ValueError), transaction() as conn:
        outbox_repo.enqueue(row, conn=conn)
    # the database itself refuses a raw insert that bypasses the repo
    with pytest.raises(psycopg.errors.CheckViolation), transaction() as conn:
        conn.execute(
            "INSERT INTO cm.outbox (kind, recipient_id, channel, body, dedup_key, template_id) "
            "VALUES ('ai_message', %s, 'telegram', 'hi', %s, %s)",
            (actors["patient_person"], f"test:{uuid4()}", uuid4()),
        )


def test_consent_state_is_as_of(actors: dict[str, Any]) -> None:
    now = clock.now()
    pid = actors["patient_person"]
    consent_repo.record_consent(
        pid, "gmail", "care_coordination", "granted", now - timedelta(days=3), "web"
    )
    consent_repo.record_consent(
        pid, "gmail", "care_coordination", "withdrawn", now - timedelta(days=1), "web"
    )
    assert (
        consent_repo.consent_state(pid, now - timedelta(days=2))["gmail"]["care_coordination"]
        == "granted"
    )
    assert consent_repo.consent_state(pid, now)["gmail"]["care_coordination"] == "withdrawn"
    assert "gmail" not in consent_repo.consent_state(pid, now - timedelta(days=5))


def test_settings_optimistic_lock(actors: dict[str, Any]) -> None:
    settings_repo.clear_cache()
    cur = settings_repo.get_setting("thresholds")
    assert cur is not None
    new = settings_repo.set_setting(
        "thresholds", cur["value"], expected_version=cur["version"], updated_by=actors["doctor"]
    )
    assert new["version"] == cur["version"] + 1
    with pytest.raises(settings_repo.VersionConflict):
        settings_repo.set_setting(
            "thresholds", cur["value"], expected_version=cur["version"], updated_by=actors["doctor"]
        )
