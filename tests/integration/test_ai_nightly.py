"""Nightly job end to end with the scripted fake model (no network) against the test database."""

import pytest

from cm.core import clock, llm
from cm.core.db import transaction
from cm.jobs import nightly
from cm.store import ai_repo, approvals_repo, outbox_repo

pytestmark = pytest.mark.usefixtures("pinned_clock")


@pytest.fixture()
def _reset_gov():
    yield
    llm.set_governor(None)


def test_nightly_fake_creates_pending_card_and_no_outbox(_reset_gov):
    out = nightly.run_patient("PT-0142", live=False, force=True)
    assert out["status"] == "done" and out["approvals"]
    assert out["tool_calls"][-1] == "submit_for_review" and out["todos"]
    with transaction() as c:
        row = approvals_repo.get(ai_repo.UUID(out["approvals"][0]), clock.now(), conn=c)
    assert row["status"] == "pending" and row["kind"] == "card" and row["payload"]["audience"] == "doctor"
    assert row["payload"]["sentences"] and all(s["refs"] for s in row["payload"]["sentences"])
    assert ai_repo.outbox_count(row["approval_id"]) == 0
    again = nightly.run_patient("PT-0142", live=False)
    assert again["status"] == "skipped"


def test_outbox_refuses_unapproved_draft():
    with transaction() as c, pytest.raises(ValueError):
        outbox_repo.enqueue({"kind": "card", "recipient_id": None, "channel": "web_inbox", "body": "x",
                             "next_attempt_at": clock.now(), "dedup_key": "t-ai-1"}, conn=c)
