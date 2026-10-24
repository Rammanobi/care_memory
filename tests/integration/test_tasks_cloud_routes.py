"""Cloud-mode /tasks/run against caremem_test: claim, replay, retry, heartbeat; migrate job exit codes."""

import time
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from cm.api.main import create_app
from cm.api.routers import tasks as router
from cm.core import lifecycle
from cm.core.db import transaction
from cm.store import task_runs_repo

pytestmark = pytest.mark.db
BASE = "https://cm-api-abc-el.a.run.app"
SA = "cm-tasks@proj.iam.gserviceaccount.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _tok(**over: Any) -> str:
    now = int(time.time())
    claims = {"iss": "https://accounts.google.com", "aud": BASE, "email": SA, "email_verified": True,
              "iat": now - 5, "exp": now + 300} | over
    return jwt.encode(claims, KEY, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture()
def calls(pinned_clock: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    monkeypatch.setenv("TASKS_MODE", "cloud")
    monkeypatch.setenv("CM_TASKS_BASE_URL", BASE)
    monkeypatch.setenv("CM_TASKS_SA", SA)
    seen: list[str] = []
    monkeypatch.setattr("cm.jobs.outbox_drainer.drain_once", lambda *a, **k: seen.append("d") or {"sent": 0})
    monkeypatch.setattr("cm.jobs.reminders.produce", lambda *a, **k: seen.append("c") or {"queued": 0})
    router.set_key_fetcher(lambda kid: KEY.public_key())
    yield seen
    router.set_key_fetcher(None)
    lifecycle.reset()


def _run(task_id: str, kind: str = "drain_outbox", tok: str | None = None, **extra: Any) -> Any:
    c = TestClient(create_app(), raise_server_exceptions=False)
    body = {"queue": "agent-runs", "task_id": task_id, "payload": {"kind": kind, **extra}}
    return c.post("/tasks/run", json=body, headers={"Authorization": f"Bearer {tok or _tok()}"})


def _tid() -> str:
    return f"it-{uuid4().hex[:12]}"


def test_runs_once_and_replay_is_acked_without_rerun(calls: list[str]) -> None:
    tid = _tid()
    r = _run(tid)
    assert r.status_code == 200 and r.json()["status"] == "ok" and calls == ["d"]
    assert task_runs_repo.get_state(tid) == "succeeded"
    r2 = _run(tid)
    assert r2.status_code == 200 and r2.json()["status"] == "duplicate"
    assert calls == ["d"]  # handler did not run again


def test_task_name_header_wins_over_body(calls: list[str]) -> None:
    tid = _tid()
    c = TestClient(create_app())
    r = c.post("/tasks/run", json={"task_id": "other-id", "payload": {"kind": "checkins"}},
               headers={"Authorization": f"Bearer {_tok()}", "X-CloudTasks-TaskName": tid})
    assert r.json()["task_id"] == tid and task_runs_repo.get_state(tid) == "succeeded"
    assert task_runs_repo.get_state("other-id") is None


def test_failure_is_retryable_then_succeeds(calls: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    tid = _tid()
    state = {"n": 0}

    def flaky(*a: Any, **k: Any) -> dict[str, int]:
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("temporary")
        return {"sent": 1}

    monkeypatch.setattr("cm.jobs.outbox_drainer.drain_once", flaky)
    assert _run(tid).status_code == 500
    assert task_runs_repo.get_state(tid) == "failed"
    r = _run(tid)
    assert r.status_code == 200 and r.json()["attempt"] == 2
    assert task_runs_repo.get_state(tid) == "succeeded"


def test_permanent_error_is_acked_not_retried(calls: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    class Invalid(ValueError):
        pass

    def bad(*a: Any, **k: Any) -> dict[str, int]:
        raise Invalid("bad payload")

    monkeypatch.setattr("cm.jobs.outbox_drainer.drain_once", bad)
    tid = _tid()
    r = _run(tid)
    assert r.status_code == 200 and r.json()["status"] == "failed"
    assert task_runs_repo.get_state(tid) == "failed"


def test_fresh_running_row_is_busy_409(calls: list[str]) -> None:
    tid = _tid()
    assert task_runs_repo.claim(tid, "drain_outbox").status == "claimed"
    r = _run(tid)
    assert r.status_code == 409 and calls == []
    # a stale heartbeat can be taken over
    with transaction() as conn:
        conn.execute("UPDATE cm.task_runs SET heartbeat_at = heartbeat_at - interval '5 minutes' "
                     "WHERE task_id=%s", (tid,))
    assert _run(tid).status_code == 200 and calls == ["d"]


def test_heartbeat_updates_row(calls: list[str]) -> None:
    tid = _tid()
    task_runs_repo.claim(tid, "drain_outbox")
    with transaction() as conn:
        conn.execute("UPDATE cm.task_runs SET heartbeat_at = heartbeat_at - interval '1 hour' "
                     "WHERE task_id=%s", (tid,))
        old = conn.execute("SELECT heartbeat_at FROM cm.task_runs WHERE task_id=%s", (tid,)).fetchone()
    task_runs_repo.heartbeat(tid)
    with transaction() as conn:
        new = conn.execute("SELECT heartbeat_at FROM cm.task_runs WHERE task_id=%s", (tid,)).fetchone()
    assert new["heartbeat_at"] > old["heartbeat_at"]


def test_heartbeat_thread_beats_during_long_handler(calls: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    beats: list[str] = []
    monkeypatch.setattr(router, "HEARTBEAT_EVERY_S", 0.05)
    monkeypatch.setattr(task_runs_repo, "heartbeat", lambda t: beats.append(t))

    def slow(*a: Any, **k: Any) -> dict[str, int]:
        time.sleep(0.3)
        return {"sent": 0}

    monkeypatch.setattr("cm.jobs.outbox_drainer.drain_once", slow)
    tid = _tid()
    assert _run(tid).status_code == 200
    assert beats and set(beats) == {tid}


def test_sigterm_flag_answers_503_and_does_not_claim(calls: list[str]) -> None:
    lifecycle.request_shutdown()
    tid = _tid()
    r = _run(tid)
    assert r.status_code == 503 and calls == []
    assert task_runs_repo.get_state(tid) is None


def test_unknown_kind_acked_and_bad_id_rejected(calls: list[str]) -> None:
    assert _run(_tid(), kind="mystery").json()["status"] == "no_handler"
    assert _run("bad:id").status_code == 400


@pytest.mark.parametrize("kind", ["tap", "ingest_event", "calendar_sync", "checkins"])
def test_other_kinds_are_dispatched(calls: list[str], kind: str) -> None:
    tid = _tid()
    assert _run(tid, kind=kind).json()["status"] == "ok"
    assert task_runs_repo.get_state(tid) == "succeeded"


def test_bad_token_runs_nothing(calls: list[str]) -> None:
    tid = _tid()
    assert _run(tid, tok=_tok(aud="https://evil.example")).status_code == 401
    assert _run(tid, tok=_tok(email="x@y.z")).status_code == 401
    assert _run(tid, tok=_tok(exp=int(time.time()) - 600)).status_code == 401
    assert calls == [] and task_runs_repo.get_state(tid) is None


def test_migrate_is_idempotent(seeded_db: None) -> None:
    from cm.jobs.migrate import run_migrations

    assert run_migrations() == []  # seeded_db already applied everything; a rerun applies nothing
    assert run_migrations() == []


def test_migrate_main_exits_nonzero_on_failure(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from cm.jobs import migrate

    def boom() -> list[str]:
        raise RuntimeError("password=secret should never be echoed")

    monkeypatch.setattr(migrate, "run_migrations", boom)
    assert migrate.main() == 1
    err = capsys.readouterr().err
    assert "FAILED" in err and "secret" not in err


def test_migrate_main_exits_zero(seeded_db: None) -> None:
    from cm.jobs import migrate

    assert migrate.main() == 0
