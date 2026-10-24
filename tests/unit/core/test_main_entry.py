"""`python -m cm <command>` dispatch, Cloud SQL socket DSN and demo quiet-hours gate (fix-deploy-blockers-infra)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone

import pytest

from cm import __main__ as entry
from cm.core import config
from cm.router.quiet_hours import in_quiet_hours

NIGHT = datetime(2026, 10, 25, 20, 0, tzinfo=timezone.utc)  # 01:30 IST


def test_sweeper_stub_exits_zero(capsys) -> None:
    assert entry.run_command("sweeper", []) == 0
    assert "not implemented" in capsys.readouterr().out


def test_unknown_command_exit_2() -> None:
    assert entry.run_command("nope", []) == 2


@pytest.mark.parametrize(
    ("cmd", "module"),
    [("migrate", "migrate"), ("drain-outbox", "outbox_drainer"), ("nightly", "nightly"), ("reminders", "reminders")],
)
def test_job_commands_dispatch(monkeypatch, cmd: str, module: str) -> None:
    seen: dict = {}

    def fake_run(name, run_name=None, alter_sys=False):  # noqa: ANN001
        seen["name"], seen["argv"] = name, list(sys.argv)

    monkeypatch.setattr(entry.runpy, "run_module", fake_run)
    assert entry.run_command(cmd, ["--x"]) == 0
    assert seen["name"] == f"cm.jobs.{module}"
    assert "--x" in seen["argv"]
    assert ("--once" in seen["argv"]) == (cmd == "drain-outbox")


def test_exit_code_propagates(monkeypatch) -> None:
    def boom(*a, **k):  # noqa: ANN002, ANN003
        raise SystemExit(1)

    monkeypatch.setattr(entry.runpy, "run_module", boom)
    assert entry.run_command("migrate", []) == 1


def test_main_argv_runs_command(monkeypatch) -> None:
    monkeypatch.setattr(entry, "run_command", lambda c, a: 0 if c == "sweeper" else 9)
    with pytest.raises(SystemExit) as e:
        entry.main(["sweeper"])
    assert e.value.code == 0


def test_dsn_cloudsql_instance_and_socket_host() -> None:
    assert config.resolve_db_host({"CLOUD_SQL_INSTANCE": "p:r:i"}) == "/cloudsql/p:r:i"
    assert config.resolve_db_host({"DB_HOST": "/cloudsql/p:r:i", "CLOUD_SQL_INSTANCE": "x"}) == "/cloudsql/p:r:i"
    assert config.resolve_db_host({}) == "localhost"
    s = config.Settings("/cloudsql/p:r:i", 5432, "caremem", "cm_app", "pa ss'w", "k", False)
    assert s.dsn == "host=/cloudsql/p:r:i port=5432 dbname=caremem user=cm_app password='pa ss\\'w'"


@pytest.mark.parametrize(("env", "ignored"), [("demo", True), ("dev", True), ("prod", False), ("", False)])
def test_quiet_hours_override(monkeypatch, env: str, ignored: bool) -> None:
    monkeypatch.setenv("DEMO_IGNORE_QUIET_HOURS", "1")
    monkeypatch.setenv("CM_ENV", env)
    assert in_quiet_hours(NIGHT) is (not ignored)


def test_quiet_hours_flag_off(monkeypatch) -> None:
    monkeypatch.setenv("DEMO_IGNORE_QUIET_HOURS", "0")
    monkeypatch.setenv("CM_ENV", "demo")
    assert in_quiet_hours(NIGHT) is True
