"""AUTH_MODE=firebase in current_user and /auth: fake verifier + fake DB row (no network, no DB)."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from cm.api import firebase_auth
from cm.api.main import create_app

PID = str(uuid4())
ROW: dict[str, Any] = {}


class _Result:
    def __init__(self, row: Any) -> None:
        self.row = row

    def fetchone(self) -> Any:
        return self.row


class _Conn:
    def execute(self, sql: str, params: Any = None) -> _Result:
        if "identity_vault" in sql:
            return _Result(None)
        return _Result(dict(ROW) if ROW and params and str(params[0]) == PID else None)


@contextmanager
def _tx() -> Iterator[_Conn]:
    yield _Conn()


def _fake_verify(token: str) -> dict[str, Any]:
    """Token text 'good:<role>:<tv>' or 'noclaims'; anything else is rejected."""
    if token == "noclaims":
        return {"sub": "uid-x"}
    parts = token.split(":")
    if parts[0] != "good":
        raise firebase_auth.FirebaseAuthError("invalid_signature_or_claims")
    return {"sub": "uid-1", "role": parts[1], "pid": PID, "tv": int(parts[2])}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("AUTH_MODE", "firebase")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "demo-project")
    monkeypatch.setattr("cm.api.deps.transaction", _tx)
    monkeypatch.setattr("cm.api.routers.auth.transaction", _tx)
    ROW.clear()
    ROW.update(token_version=3, active=True, username="dr.rao", token="P-0001", role="doctor",
               clinic_id=None, district_id=None)
    firebase_auth.set_verifier(_fake_verify)
    yield TestClient(create_app())
    firebase_auth.set_verifier(None)


def _me(c: TestClient, tok: str | None) -> Any:
    return c.get("/auth/me", headers={"Authorization": f"Bearer {tok}"} if tok else {})


def test_valid_token_matching_db(client: TestClient) -> None:
    r = _me(client, "good:doctor:3")
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "doctor" and r.json()["username"] == "dr.rao"


def test_invalid_token_401(client: TestClient) -> None:
    assert _me(client, "forged").status_code == 401
    assert _me(client, None).status_code == 401


def test_no_claims_403(client: TestClient) -> None:
    r = _me(client, "noclaims")
    assert r.status_code == 403 and r.json()["code"] == "no_role"


def test_role_mismatch_401(client: TestClient) -> None:
    assert _me(client, "good:admin:3").status_code == 401


def test_stale_token_version_401(client: TestClient) -> None:
    assert _me(client, "good:doctor:2").status_code == 401


def test_retired_user_401(client: TestClient) -> None:
    ROW["active"] = False
    assert _me(client, "good:doctor:3").status_code == 401


def test_password_login_disabled(client: TestClient) -> None:
    r = client.post("/auth/login", json={"username": "dr.rao", "password": "irrelevant-x"})
    assert r.status_code == 404 and r.json()["code"] == "use_firebase"


def test_firebase_without_project_refuses_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "firebase")
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    with pytest.raises(RuntimeError):
        create_app()


def test_local_mode_ignores_firebase_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTH_MODE", raising=False)
    firebase_auth.set_verifier(_fake_verify)
    try:
        c = TestClient(create_app())
        assert _me(c, "good:doctor:3").status_code == 401  # not an HS256 session token
    finally:
        firebase_auth.set_verifier(None)
