"""NoStoreMiddleware, CORS bearer from Hosting origins, and the Cloud Run env template."""

from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from cm.api.no_store import NoStoreMiddleware

ROOT = Path(__file__).resolve().parents[3]


def _app() -> TestClient:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://doc.web.app"],
        allow_methods=["GET"],
        allow_headers=["Content-Type", "Authorization", "X-CM-Client"],
    )
    app.add_middleware(NoStoreMiddleware)

    @app.get("/x")
    def x() -> dict:
        return {"ok": 1}

    return TestClient(app)


def test_bearer_gets_no_store() -> None:
    r = _app().get("/x", headers={"Authorization": "Bearer t"})
    assert r.headers["cache-control"] == "private, no-store"


def test_cookie_gets_no_store() -> None:
    c = _app()
    c.cookies.set("cm_session", "t")
    assert c.get("/x").headers["cache-control"] == "private, no-store"


def test_anonymous_untouched() -> None:
    assert "cache-control" not in _app().get("/x").headers


def test_cors_preflight_allows_authorization_from_hosting_origin() -> None:
    r = _app().options(
        "/x",
        headers={
            "Origin": "https://doc.web.app",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert r.status_code == 200
    assert "authorization" in r.headers["access-control-allow-headers"].lower()
    assert r.headers["access-control-allow-origin"] == "https://doc.web.app"


def test_api_env_template_has_cloud_vars_and_no_secrets() -> None:
    d = yaml.safe_load((ROOT / "infra/env/api.env.yaml").read_text(encoding="utf-8"))
    for k in ("AUTH_MODE", "FIREBASE_PROJECT_ID", "CORS_ORIGINS", "CM_ALLOWED_HOSTS", "TELEGRAM_BOT_USERNAME"):
        assert k in d
    assert d["AUTH_MODE"] == "firebase"
    assert not {"TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRET", "JWT_SIGNING_KEY", "OPENAI_API_KEY"} & set(d)
