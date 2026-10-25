"""scripts/firebase_users.py: dry run by default, fake admin client, never prints passwords."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from cm.core.ids import det_id

ROOT = Path(__file__).resolve().parents[3]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("firebase_users", ROOT / "scripts" / "firebase_users.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


fu = _load()
PW = "test-only-pw-0123456789"


class FakeAdmin:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.users: dict[str, dict[str, Any]] = {u: {} for u in existing or set()}
        self.log: list[str] = []

    def find_uid(self, uid: str) -> bool:
        return uid in self.users

    def create(self, uid: str, email: str, password: str) -> None:
        self.users[uid] = {"email": email, "pw": password}
        self.log.append(f"create {uid}")

    def update(self, uid: str, email: str, password: str) -> None:
        self.users[uid].update(email=email, pw=password)
        self.log.append(f"update {uid}")

    def set_claims(self, uid: str, claims: dict[str, Any] | None) -> None:
        self.users.setdefault(uid, {})["claims"] = claims

    def revoke(self, uid: str) -> None:
        self.users[uid]["disabled"] = True


def test_demo_users_match_seed_accounts() -> None:
    users = {u.username: u for u in fu.demo_users()}
    assert set(users) == {"dr.rao", "admin.demo", "ravi.pt0142", "lakshmi.s01", "demo.pt0906", "demo.pt0960"}
    assert users["dr.rao"].claims == {"role": "doctor", "pid": str(det_id("person", "D-01")), "tv": 1}
    assert users["demo.pt0960"].role == "patient"
    assert fu.demo_users({"dr.rao": 3})[0].tv == 3


def test_dry_run_is_default_and_needs_nothing(capsys: pytest.CaptureFixture[str],
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_USER_PASSWORDS", json.dumps({"dr.rao": PW}))
    fake = FakeAdmin()
    assert fu.main([], client=fake) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "dr.rao: would create/update dr.rao@users.carememory.app" in out
    assert fake.log == [] and PW not in out


def test_apply_creates_then_updates_idempotently(capsys: pytest.CaptureFixture[str],
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    pws = {u.username: PW for u in fu.demo_users()}
    pws["lakshmi.s01"] = "short"
    monkeypatch.setenv("DEMO_USER_PASSWORDS", json.dumps(pws))
    fake = FakeAdmin()
    assert fu.main(["--apply"], client=fake) == 0
    out = capsys.readouterr().out
    assert "dr.rao: created, claims ok" in out and "lakshmi.s01: skipped" in out
    assert PW not in out and "short" not in out
    assert fake.users["cm-dr-rao"]["claims"]["role"] == "doctor"
    assert "cm-lakshmi-s01" not in fake.users
    fu.main(["--apply"], client=fake)
    assert "dr.rao: updated, claims ok" in capsys.readouterr().out


def test_revoke(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeAdmin({"cm-demo-pt0960"})
    fu.main(["--revoke", "demo.pt0960"], client=fake)
    assert "would disable" in capsys.readouterr().out and "disabled" not in fake.users["cm-demo-pt0960"]
    fu.main(["--revoke", "demo.pt0960", "--apply"], client=fake)
    assert fake.users["cm-demo-pt0960"] == {"claims": None, "disabled": True}
    assert fu.main(["--revoke", "nobody"], client=fake) == 2


def test_apply_without_project_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    assert fu.main(["--apply"]) == 2
