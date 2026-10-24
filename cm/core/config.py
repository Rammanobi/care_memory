"""Lane A: typed settings read from the environment (and a git-ignored .env for local dev)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from .env into os.environ without overriding real env vars."""
    p = path or REPO_ROOT / ".env"
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
            val = val[1:-1]
        os.environ.setdefault(key.strip(), val)


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _q(v: str) -> str:
    """Quote a libpq conninfo value only when needed (spaces, quotes, backslashes, empty)."""
    if v and not any(c in v for c in " '\\"):
        return v
    return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"


def resolve_db_host(env: Mapping[str, str]) -> str:
    """DB_HOST wins. Else CLOUD_SQL_INSTANCE -> /cloudsql/<instance>."""
    host = env.get("DB_HOST", "").strip()
    if host:
        return host
    inst = env.get("CLOUD_SQL_INSTANCE", "").strip()
    if inst:
        return inst if inst.startswith("/") else f"/cloudsql/{inst}"
    return "localhost"


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    jwt_signing_key: str
    demo_mode: bool
    jwt_ttl_min: int = 480
    pool_min: int = 1
    pool_max: int = 5
    cors_origins: tuple[str, ...] = field(default=("http://localhost:5173",))
    cookie_secure: bool = False
    cookie_domain: str | None = None

    @property
    def dsn(self) -> str:
        """libpq key/value DSN. A host starting with "/" is a unix-socket directory (Cloud SQL)."""
        return (
            f"host={_q(self.db_host)} port={self.db_port} dbname={_q(self.db_name)} "
            f"user={_q(self.db_user)} password={_q(self.db_password)}"
        )


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """Read settings from env. Secrets have no defaults except the local-only db password."""
    load_dotenv()
    env = os.environ
    return Settings(
        db_host=resolve_db_host(env),
        db_port=int(env.get("DB_PORT", "5432")),
        db_name=env.get("DB_NAME", "caremem"),
        db_user=env.get("DB_USER", "postgres"),
        db_password=env.get("DB_PASSWORD", ""),
        jwt_signing_key=env.get("JWT_SIGNING_KEY", ""),
        demo_mode=_flag("DEMO_MODE"),
        jwt_ttl_min=int(env.get("JWT_TTL_MIN", "480")),
        pool_min=int(env.get("DB_POOL_MIN", "1")),
        pool_max=int(env.get("DB_POOL_MAX", "5")),
        cors_origins=tuple(
            o.strip()
            for o in env.get("CORS_ORIGINS", "http://localhost:5173").split(",")
            if o.strip()
        ),
        cookie_secure=_flag("COOKIE_SECURE") or env.get("CM_ENV", "").strip().lower() == "prod",
        cookie_domain=env.get("CM_COOKIE_DOMAIN", "").strip() or None,
    )
