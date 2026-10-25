"""Live patient app: no invented fields, and every /portal response is free of banned terms."""

import re
from typing import Any

import pytest

from cm.api.suppress import find_banned
from tests.integration.test_e2e_api import _as

pytestmark = pytest.mark.db


@pytest.fixture()
def app_client(pinned_clock: None) -> None:
    """Seeded test database with the pinned clock (the tests log in per user)."""


PATIENT_GETS = [
    "/me",
    "/today",
    "/record",
    "/requests",
    "/consents",
    "/documents",
    "/medicines",
    "/inbox",
    "/answers",
]
SUPPORTER_GETS = ["/supporter/checkin", "/inbox"]


def _all_strings(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in _all_strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in _all_strings(v)]
    return []


@pytest.mark.parametrize(
    "user,paths", [("ravi.pt0142", PATIENT_GETS), ("lakshmi.s01", SUPPORTER_GETS)]
)
def test_no_banned_terms_in_any_portal_response(
    app_client: None, user: str, paths: list[str]
) -> None:
    c = _as(user)
    for path in paths:
        r = c.get(f"/portal{path}")
        assert r.status_code == 200, (path, r.text)
        for s in _all_strings(r.json()):
            assert find_banned(s) == [], (path, s)


def test_me_never_invents_relation_or_reminder(app_client: None) -> None:
    me = _as("ravi.pt0142").get("/portal/me").json()
    rem = me["reminder"]
    assert rem is None or re.fullmatch(r"\d{1,2}:\d{2} (am|pm)", rem)
    sup = me["supporter"]
    assert sup is None or sup["relation"] is None or sup["relation"].strip()
    view = _as("lakshmi.s01").get("/portal/supporter/checkin").json()
    assert view["relation"] is None or view["relation"].strip()
