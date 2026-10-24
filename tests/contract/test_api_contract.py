"""API contract checks against /openapi.json (additions only; the frozen contracts are not touched).

1. Every route needs a session except health, login and the Telegram webhook.
2. 200 responses validate against the route's declared response_model, for every role.
3. A seeded hand-written fuzz loop over GET routes (query + path params) never gets a 5xx.
Read-only: the fuzz only sends GETs; /stream (SSE, never ends) is skipped.
"""

from __future__ import annotations

import json
import os
import random
import re
import string
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from cm.api.main import create_app
from cm.api.routers.auth import reset_rate_limits
from cm.core.db import transaction

pytestmark = pytest.mark.db
WEB = {"X-CM-Client": "web"}
PUBLIC = {
    ("GET", "/healthz"),
    ("GET", "/readyz"),
    ("POST", "/auth/login"),
    ("POST", "/webhooks/telegram"),  # authenticated by the Telegram secret header instead
}
USERS = ("dr.rao", "admin.demo", "ravi.pt0142", "lakshmi.s01")
NO_FUZZ = {"/stream"}


@pytest.fixture(scope="module")
def app(seeded_db: None) -> Any:
    return create_app()


@pytest.fixture()
def clients(app: Any, pinned_clock: None) -> Iterator[dict[str, TestClient]]:
    reset_rate_limits()
    pw = json.loads(os.environ["DEMO_USER_PASSWORDS"])
    out = {}
    for u in USERS:
        c = TestClient(app, headers=WEB, raise_server_exceptions=False)
        r = c.post("/auth/login", json={"username": u, "password": pw[u]})
        assert r.status_code == 200, (u, r.status_code)
        out[u] = c
    yield out


def _operations(app: Any) -> list[tuple[str, str, dict[str, Any]]]:
    ops = []
    for path, item in app.openapi()["paths"].items():
        for method, op in item.items():
            ops.append((method.upper(), path, op))
    return ops


def _fill(path: str, value: str = "") -> str:
    return re.sub(r"\{[^}]+\}", value or str(uuid4()), path)


def test_every_route_requires_auth_except_public(app: Any, pinned_clock: None) -> None:
    anon = TestClient(app, headers=WEB, raise_server_exceptions=False)
    seen = set()
    for method, path, _op in _operations(app):
        seen.add((method, path))
        if (method, path) in PUBLIC:
            continue
        r = anon.request(method, _fill(path), json={} if method in {"POST", "PUT", "PATCH"} else None)
        assert r.status_code == 401, f"{method} {path} answered {r.status_code} without a session"
        assert r.json().get("code") == "unauthenticated", (method, path, r.text[:200])
    assert seen >= PUBLIC, PUBLIC - seen


def test_forged_or_expired_tokens_are_refused(app: Any, pinned_clock: None) -> None:
    import jwt

    bad = [
        "not-a-jwt",
        jwt.encode({"sub": "x", "role": "admin"}, "wrong-key-for-tests-only-000000", algorithm="HS256"),
        jwt.encode({"sub": "x", "role": "admin"}, "", algorithm="none") if hasattr(jwt, "encode") else "",
    ]
    for tok in bad:
        c = TestClient(app, headers={**WEB, "Authorization": f"Bearer {tok}"}, raise_server_exceptions=False)
        for path in ("/auth/me", "/review/queue", "/admin/settings", "/portal/me"):
            r = c.get(path)
            assert r.status_code == 401, (path, r.status_code)


def _response_models(app: Any) -> dict[tuple[str, str], Any]:
    out = {}
    for r in app.routes:
        if isinstance(r, APIRoute) and r.response_model is not None:
            for m in r.methods:
                out[(m, r.path)] = r.response_model
    return out


def test_get_responses_validate_against_response_models(
    app: Any, clients: dict[str, TestClient]
) -> None:
    models = _response_models(app)
    checked = 0
    for method, path, _op in _operations(app):
        if method != "GET" or "{" in path or path in NO_FUZZ:
            continue
        for user, c in clients.items():
            r = c.get(path)
            assert r.status_code < 500, f"{user} GET {path} -> {r.status_code}"
            assert r.status_code in (200, 204, 400, 403, 404, 409, 422), (user, path, r.status_code)
            if r.status_code == 200 and (method, path) in models:
                TypeAdapter(models[(method, path)]).validate_python(r.json())
                checked += 1
            if r.status_code >= 400:
                body = r.json()
                assert body.get("status") == r.status_code and body.get("code"), (path, body)
    assert checked >= 5  # every GET route that declares a model and answers 200 for some role


def _known_ids() -> dict[str, list[str]]:
    with transaction() as conn:
        aps = [str(r["approval_id"]) for r in conn.execute("SELECT approval_id FROM cm.approvals LIMIT 20")]
        pts = [r["token"] for r in conn.execute("SELECT token FROM cm.persons WHERE role='patient'")]
        pids = [str(r["patient_id"]) for r in conn.execute("SELECT patient_id FROM cm.patients")]
        people = [str(r["person_id"]) for r in conn.execute("SELECT person_id FROM cm.persons LIMIT 20")]
        clinics = [str(r["clinic_id"]) for r in conn.execute("SELECT clinic_id FROM cm.clinics")]
        evs = [f"E:{r['event_id']}" for r in conn.execute("SELECT event_id FROM cm.events LIMIT 20")]
        obx = [str(r["outbox_id"]) for r in conn.execute("SELECT outbox_id FROM cm.outbox LIMIT 20")]
    return {"approval_id": aps, "pid": pts + pids, "person_id": people, "clinic_id": clinics,
            "ref": evs, "outbox_id": obx, "request_id": aps}  # fmt: skip


NASTY = [
    "", " ", "0", "-1", "999999999999999999999", "1e309", "NaN", "null", "true", "[]", "{}",
    "' OR 1=1 --", "%00", "..%2F..%2Fetc", "\u0000", "టీబీ", "😀" * 5, "a" * 3000, "P-0142",
    "red", "amber", "green", "pending", "E:not-a-uuid", "B:", "2026-13-45", str(uuid4()),
]  # fmt: skip


def _value(r: random.Random, name: str, known: dict[str, list[str]]) -> str:
    roll = r.random()
    if roll < 0.35 and known.get(name):
        return r.choice(known[name])
    if roll < 0.7:
        return r.choice(NASTY)
    alphabet = string.printable + "ఈరోజుमें"
    return "".join(r.choice(alphabet) for _ in range(r.randint(0, 40)))


def _fuzz(app: Any, clients: dict[str, TestClient], seed: int, n: int) -> None:
    r = random.Random(seed)  # noqa: S311  (seeded fuzz)
    known = _known_ids()
    gets = [(p, op) for m, p, op in _operations(app) if m == "GET" and p not in NO_FUZZ]
    failures = []
    for _ in range(n):
        path, op = r.choice(gets)
        params = [p for p in op.get("parameters", []) if p["in"] in ("query", "path")]
        q: dict[str, str] = {}
        url = path
        for p in params:
            if p["in"] == "path":
                url = url.replace("{" + p["name"] + "}", quote(_value(r, p["name"], known), safe="") or "x")
            elif r.random() < 0.8:
                q[p["name"]] = _value(r, p["name"], known)
        if r.random() < 0.2:
            q[_value(r, "junk", known)[:20] or "zz"] = _value(r, "junk", known)  # unknown param
        user = r.choice(USERS)
        try:
            resp = clients[user].get(url, params=q)
        except Exception as exc:  # noqa: BLE001  (a client-side crash is a finding too)
            failures.append((user, url, q, repr(exc)[:200]))
            continue
        if resp.status_code >= 500:
            failures.append((user, url, q, resp.status_code, resp.text[:200]))
    assert not failures, failures[:5]


def test_fuzzed_get_params_never_500(app: Any, clients: dict[str, TestClient]) -> None:
    _fuzz(app, clients, seed=20261024, n=150)


@pytest.mark.slow
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_fuzzed_get_params_never_500_long(app: Any, clients: dict[str, TestClient], seed: int) -> None:
    _fuzz(app, clients, seed=seed, n=500)
