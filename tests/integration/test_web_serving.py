"""Production web serving: SPA fallback, cache headers, API not shadowed, Host validation, cookie flags."""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cm.api.main import create_app
from cm.api.routers.auth import reset_rate_limits
from cm.api.web import host_allowed, parse_hosts
from cm.core.config import load_settings

pytestmark = pytest.mark.db
WEB = {"X-CM-Client": "web"}
HTML = {"accept": "text/html"}


@pytest.fixture()
def dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>CareMemory</title><div id=root>")
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    monkeypatch.setenv("CM_WEB_DIR", str(tmp_path))
    return tmp_path


def _client(**kw: object) -> TestClient:
    return TestClient(create_app(), **kw)  # type: ignore[arg-type]


def test_root_and_spa_routes_serve_index(seeded_db: None, dist: Path) -> None:
    with _client() as c:
        for path in ("/", "/doctor", "/doctor/patients/abc", "/patient/record", "/supporter"):
            r = c.get(path, headers=HTML)
            assert r.status_code == 200, path
            assert "<div id=root>" in r.text
            assert r.headers["cache-control"] == "no-cache"


def test_root_without_accept_header(seeded_db: None, dist: Path) -> None:
    with _client() as c:
        assert c.get("/", headers={"accept": "*/*"}).status_code == 200
        assert c.get("/doctor", headers={"accept": "*/*"}).status_code == 200
        assert c.get("/doctor", headers={"accept": "application/json"}).status_code == 404


def test_assets_are_immutable_and_files_served(seeded_db: None, dist: Path) -> None:
    with _client() as c:
        r = c.get("/assets/app-abc123.js")
        assert r.status_code == 200
        assert "immutable" in r.headers["cache-control"]
        assert c.get("/favicon.svg").status_code == 200
        assert c.get("/assets/missing.js").status_code == 404
        assert c.get("/..%2f..%2fetc%2fpasswd", headers=HTML).status_code in (200, 404)


def test_api_routes_not_shadowed(seeded_db: None, dist: Path) -> None:
    with _client() as c:
        assert c.get("/healthz").json() == {"status": "ok"}
        assert c.get("/openapi.json").json()["info"]["title"] == "CareMemory"
        r = c.get("/auth/me", headers=WEB)
        assert r.status_code == 401
        assert r.headers["content-type"].startswith("application/json")
        # unknown non-HTML (API-style) paths stay JSON 404, not index.html
        miss = c.get("/auth/nope", headers={"accept": "application/json"})
        assert miss.status_code == 404
        assert miss.headers["content-type"].startswith("application/json")


def test_no_web_dir_means_api_only(
    seeded_db: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CM_WEB_DIR", str(tmp_path / "none"))
    with _client() as c:
        assert c.get("/", headers=HTML).status_code == 404
        assert c.get("/healthz").status_code == 200


def test_host_validation(seeded_db: None, dist: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CM_ALLOWED_HOSTS", "care.example.com, *.clinic.example.org")
    with _client() as c:
        assert c.get("/", headers={**HTML, "host": "care.example.com"}).status_code == 200
        assert c.get("/", headers={**HTML, "host": "care.example.com:8443"}).status_code == 200
        assert c.get("/", headers={**HTML, "host": "a.clinic.example.org"}).status_code == 200
        assert c.get("/", headers={**HTML, "host": "evil.test"}).status_code == 400
        assert c.get("/auth/me", headers={**WEB, "host": "evil.test"}).status_code == 400
        assert c.get("/healthz", headers={"host": "10.0.0.7"}).status_code == 200  # probes exempt


def test_host_matching_rules() -> None:
    allowed = parse_hosts("Care.Example.com,*.x.org")
    assert host_allowed("care.example.com", allowed)
    assert host_allowed("a.b.x.org:80", allowed)
    assert not host_allowed("x.org", allowed)
    assert not host_allowed("care.example.com.evil.test", allowed)
    assert host_allowed("anything", ())  # unset = allow all (dev)


def test_cookie_flags_from_env(
    seeded_db: None, dist: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CM_ENV", "prod")
    monkeypatch.setenv("CM_COOKIE_DOMAIN", ".example.com")
    load_settings.cache_clear()
    reset_rate_limits()
    try:
        user = "dr.rao"
        pw = json.loads(os.environ["DEMO_USER_PASSWORDS"])[user]
        with _client(headers=WEB, base_url="https://care.example.com") as c:
            r = c.post("/auth/login", json={"username": user, "password": pw})
            assert r.status_code == 200, r.text
            cookie = r.headers["set-cookie"].lower()
            assert "secure" in cookie and "domain=.example.com" in cookie and "httponly" in cookie
    finally:
        load_settings.cache_clear()
