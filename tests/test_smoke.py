"""Boot smoke test: the API app imports and /healthz answers."""

from fastapi.testclient import TestClient

from cm.api.main import app


def test_healthz_returns_ok() -> None:
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
