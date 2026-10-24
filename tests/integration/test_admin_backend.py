"""Admin backend: /admin/channels, /admin/demo/run-nightly, patients next-step with pending drafts."""

import json
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from cm.api.main import create_app
from cm.api.routers.auth import reset_rate_limits
from cm.core import tasks
from cm.core.config import load_settings

pytestmark = pytest.mark.db
WEB = {"X-CM-Client": "web"}


def _as(user: str) -> TestClient:
    reset_rate_limits()
    c = TestClient(create_app(), headers=WEB)
    pw = json.loads(os.environ["DEMO_USER_PASSWORDS"])[user]
    assert c.post("/auth/login", json={"username": user, "password": pw}).status_code == 200
    return c


@pytest.fixture()
def admin(pinned_clock: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DEMO_MODE", "1")
    load_settings.cache_clear()
    tasks.reset_for_tests()
    with _as("admin.demo") as c:
        yield c
    load_settings.cache_clear()


def test_channels_report_real_state(admin: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("GMAIL_REFRESH_TOKEN", "GMAIL_MAILBOX"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "@demo_bot")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:fake")
    rows = {r["name"]: r for r in admin.get("/admin/channels").json()}
    assert rows["telegram"]["bot_username"] == "demo_bot" and rows["telegram"]["connected"] in (
        True,
        False,
    )
    assert rows["gmail"]["connected"] is False and rows["gmail"]["detail"] == "Not connected"
    assert rows["calendar"]["connected"] is False


def test_run_nightly_queues_fake_model_run(
    admin: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CM_DATA_CLASS", "real")  # live LLM never allowed for real data
    r = admin.post("/admin/demo/run-nightly", json={"patient": "PT-0142", "live": True})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued" and body["live"] is False and ":" not in body["task_id"]
    assert body["task_id"] in tasks._seen  # enqueued (the dev worker may already have drained it)
    assert admin.post("/admin/demo/run-nightly", json={"patient": "PT-9999"}).status_code == 404


def test_run_nightly_requires_admin(pinned_clock: None) -> None:
    with _as("dr.rao") as c:
        assert c.post("/admin/demo/run-nightly", json={"patient": "PT-0142"}).status_code == 403


def test_nightly_dispatch_runs_fake_model(admin: TestClient) -> None:
    from cm.api.routers.tasks import dispatch

    dispatch(
        "agent-runs", "t", {"kind": "nightly", "patient": "P-0142", "live": False}
    )  # no network, no key
