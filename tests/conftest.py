"""Shared pytest fixtures. DB tests (marker `db`) run against a separate database (caremem_test)."""

import os
import secrets
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cm.core.config import load_dotenv, load_settings  # noqa: E402

load_dotenv()
# Never touch the dev database: tests always use their own.
os.environ["DEMO_IGNORE_QUIET_HOURS"] = "0"  # dev .env demo switch must not change test behaviour
os.environ.setdefault("CM_WEB_DIR", os.path.join(os.path.dirname(__file__), "_no_web_dist"))  # API tests never serve a built web/dist
os.environ["CM_ENV"] = "test"  # load_settings() reloads .env; setdefault semantics keep these
os.environ["DB_NAME"] = os.environ.get("CM_TEST_DB_NAME", "caremem_test")
os.environ.setdefault("JWT_SIGNING_KEY", "test-" + secrets.token_hex(24))
os.environ.setdefault("DB_PASSWORD", "postgres")  # local compose default; tests only
os.environ["LOGIN_PER_IP_PER_MIN"] = "1000"
os.environ["LOGIN_PER_USER_PER_MIN"] = "1000"
load_settings.cache_clear()


def _ensure_database() -> None:
    import psycopg

    s = load_settings()
    with psycopg.connect(
        f"host={s.db_host} port={s.db_port} dbname=postgres user={s.db_user} password={s.db_password}",
        autocommit=True,
        connect_timeout=3,
    ) as c:
        if not c.execute("SELECT 1 FROM pg_database WHERE datname=%s", (s.db_name,)).fetchone():
            c.execute(f'CREATE DATABASE "{s.db_name}"')  # noqa: S608 (fixed test db name)


@pytest.fixture(scope="session")
def seeded_db() -> Iterator[None]:
    """Create/migrate the test database and load the small seed once per session."""
    try:
        _ensure_database()
    except Exception as exc:  # database not running
        pytest.skip(f"Postgres not reachable ({type(exc).__name__}); run `docker compose up -d db`")
    from cm.jobs.seed import run_seed

    run_seed(small=True, reset=True)
    yield


@pytest.fixture()
def pinned_clock(seeded_db: None) -> Iterator[None]:
    from cm.core import clock
    from cm.core.db import transaction

    with transaction() as conn:
        clock.load_pin(conn)
    yield
    clock.unpin()
