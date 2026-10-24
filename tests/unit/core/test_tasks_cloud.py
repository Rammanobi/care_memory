"""cm.core.tasks cloud mode: Cloud Tasks HTTP task creation through an injected fake client."""

import json
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest

from cm.core import clock, tasks

BASE = "https://cm-api-abc-el.a.run.app"
SA = "cm-tasks@proj.iam.gserviceaccount.com"
_QUEUE_VARS = (
    "CM_TASKS_QUEUE_AGENT_RUNS", "TASKS_QUEUE_AGENT_RUNS", "CM_TASKS_QUEUE_OUTBOUND",
    "TASKS_QUEUE_OUTBOUND", "CM_TASKS_QUEUE_RESUMES", "TASKS_QUEUE_RESUMES",
)


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.raises: Exception | None = None

    def create_task(self, request: dict[str, Any]) -> Any:
        self.calls.append(request)
        if self.raises:
            raise self.raises
        return object()


class AlreadyExists(Exception):  # same class name as google.api_core.exceptions.AlreadyExists
    pass


@pytest.fixture()
def cloud(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeClient]:
    env = {"TASKS_MODE": "cloud", "CM_TASKS_BASE_URL": BASE + "/", "CM_TASKS_SA": SA,
           "GCP_PROJECT": "proj", "GCP_REGION": "asia-south1"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    for k in _QUEUE_VARS:
        monkeypatch.delenv(k, raising=False)
    fake = FakeClient()
    tasks.set_cloud_client(fake)
    yield fake
    tasks.set_cloud_client(None)


def test_creates_named_http_task_with_oidc(cloud: FakeClient) -> None:
    tasks.enqueue("agent-runs", "tg-42", {"kind": "tap", "update_id": 42})
    (req,) = cloud.calls
    parent = "projects/proj/locations/asia-south1/queues/agent-runs"
    assert req["parent"] == parent
    t = req["task"]
    assert t["name"] == f"{parent}/tasks/tg-42"
    h = t["http_request"]
    assert h["url"] == f"{BASE}/tasks/run" and h["http_method"] == "POST"
    assert h["oidc_token"] == {"service_account_email": SA, "audience": BASE}
    assert json.loads(h["body"]) == {
        "queue": "agent-runs", "task_id": "tg-42", "payload": {"kind": "tap", "update_id": 42},
    }
    assert "schedule_time" not in t


def test_queue_names_come_from_env(cloud: FakeClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CM_TASKS_QUEUE_OUTBOUND", "outbound-x")
    tasks.enqueue("outbound", "drain-telegram-1", {"kind": "drain_outbox"})
    assert cloud.calls[0]["parent"].endswith("/queues/outbound-x")


def test_delay_sets_schedule_time(cloud: FakeClient) -> None:
    clock.pin(datetime(2026, 10, 25, 12, 0, tzinfo=UTC))
    try:
        tasks.enqueue("resumes", "resume-1", {"kind": "x"}, delay_s=90)
    finally:
        clock.unpin()
    assert cloud.calls[0]["task"]["schedule_time"] == datetime(2026, 10, 25, 12, 1, 30, tzinfo=UTC)


def test_already_exists_is_success(cloud: FakeClient) -> None:
    cloud.raises = AlreadyExists("409")
    tasks.enqueue("agent-runs", "same-id", {})  # no exception
    assert len(cloud.calls) == 1


def test_other_errors_propagate(cloud: FakeClient) -> None:
    cloud.raises = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        tasks.enqueue("agent-runs", "t1", {})


@pytest.mark.parametrize("bad", ["a:b", "", "x y", "a/b", "x" * 501])
def test_task_id_must_be_colon_free_and_safe(cloud: FakeClient, bad: str) -> None:
    with pytest.raises(ValueError):
        tasks.enqueue("agent-runs", bad, {})
    assert cloud.calls == []


@pytest.mark.parametrize("missing", ["CM_TASKS_BASE_URL", "CM_TASKS_SA", "GCP_PROJECT"])
def test_missing_config_fails_loudly(
    cloud: FakeClient, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.delenv(missing, raising=False)
    monkeypatch.delenv("TASKS_INVOKER_SA", raising=False)
    with pytest.raises(tasks.TasksConfigError):
        tasks.enqueue("agent-runs", "t1", {})
    assert cloud.calls == []


def test_missing_library_without_injected_client(monkeypatch: pytest.MonkeyPatch) -> None:
    tasks.set_cloud_client(None)
    env = {"TASKS_MODE": "cloud", "CM_TASKS_BASE_URL": BASE, "CM_TASKS_SA": SA,
           "GCP_PROJECT": "p", "GCP_REGION": "r"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setitem(sys.modules, "google.cloud.tasks_v2", None)  # makes the import fail
    with pytest.raises(tasks.TasksConfigError):
        tasks.enqueue("agent-runs", "t1", {})


def test_local_mode_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TASKS_MODE", "local")
    tasks.reset_for_tests()
    tasks.enqueue("agent-runs", "dup", {"a": 1})
    tasks.enqueue("agent-runs", "dup", {"a": 1}, delay_s=5)
    assert tasks.pending() == 1
    tasks.reset_for_tests()
