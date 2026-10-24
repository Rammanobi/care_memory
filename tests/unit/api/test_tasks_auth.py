"""/tasks/* in cloud mode: Google OIDC verification with locally generated RSA keys (no network, no DB)."""

import time
from collections.abc import Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from cm.api.main import create_app
from cm.api.routers import tasks as router
from cm.core import tasks as core_tasks

BASE = "https://cm-api-abc-el.a.run.app"
SA = "cm-tasks@proj.iam.gserviceaccount.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(*, aud: str = BASE, email: str = SA, exp_in: int = 300, key: Any = KEY,
          verified: bool = True, iss: str = "https://accounts.google.com") -> str:
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "email": email, "email_verified": verified,
              "iat": now - 10, "exp": now + exp_in}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture()
def ran(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    monkeypatch.setenv("TASKS_MODE", "cloud")
    monkeypatch.setenv("CM_TASKS_BASE_URL", BASE)
    monkeypatch.setenv("CM_TASKS_SA", SA)
    calls: list[str] = []

    def fake_drain(*a: Any, **k: Any) -> dict[str, int]:
        calls.append("drain")
        return {"sent": 0}

    monkeypatch.setattr("cm.jobs.outbox_drainer.drain_once", fake_drain)
    router.set_key_fetcher(lambda kid: KEY.public_key() if kid == "k1" else None)
    yield calls
    router.set_key_fetcher(None)


@pytest.fixture()
def client(ran: list[str]) -> TestClient:
    return TestClient(create_app())


def _call(c: TestClient, tok: str | None) -> Any:
    return c.post("/tasks/drain-outbox", headers={"Authorization": f"Bearer {tok}"} if tok else {})


def test_valid_token_runs_drain(client: TestClient, ran: list[str]) -> None:
    r = _call(client, token())
    assert r.status_code == 200 and r.json() == {"sent": 0}
    assert ran == ["drain"]


def test_scheduler_can_call_repeatedly(client: TestClient) -> None:
    assert _call(client, token()).status_code == 200
    assert _call(client, token()).status_code == 200


@pytest.mark.parametrize(
    "tok",
    [
        None,
        "not-a-jwt",
        token(aud="https://evil.example"),
        token(email="attacker@proj.iam.gserviceaccount.com"),
        token(exp_in=-600),
        token(key=OTHER),
        token(verified=False),
        token(iss="https://evil.example"),
    ],
)
def test_bad_tokens_fail_closed(client: TestClient, ran: list[str], tok: str | None) -> None:
    assert _call(client, tok).status_code == 401
    assert ran == []


def test_unsigned_alg_none_refused(client: TestClient) -> None:
    t = jwt.encode({"aud": BASE, "email": SA, "exp": int(time.time()) + 99}, "", algorithm="none")
    assert _call(client, t).status_code == 401


def test_unconfigured_fails_closed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CM_TASKS_SA")
    monkeypatch.delenv("TASKS_INVOKER_SA", raising=False)
    assert _call(client, token()).status_code == 401


def test_key_fetch_failure_fails_closed(client: TestClient) -> None:
    def boom(kid: str | None) -> Any:
        raise OSError("network down")

    router.set_key_fetcher(boom)
    assert _call(client, token()).status_code == 401


def test_every_route_is_guarded(client: TestClient) -> None:
    for path in ("/tasks/run", "/tasks/drain-outbox", "/tasks/checkins", "/tasks/checkin-nudge"):
        r = client.post(path, json={"task_id": "x", "payload": {"kind": "drain_outbox"}})
        assert r.status_code == 401, path


def test_local_mode_still_needs_admin_login(
    client: TestClient, ran: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TASKS_MODE", "local")
    assert core_tasks.mode() == "local"
    assert _call(client, token()).status_code == 401  # an OIDC token is not a session
    assert ran == []
