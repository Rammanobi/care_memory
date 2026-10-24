"""Lane A: plain ordered SQL migration runner with a schema_migrations table.

Usage: python -m cm.jobs.migrate
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from cm.core.db import connect_direct

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "store" / "migrations"
_LOCK_ID = 774411


def _files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def run_migrations() -> list[str]:
    """Apply pending migrations in order; return the names applied now."""
    applied_now: list[str] = []
    with connect_direct() as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_ID,))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS public.schema_migrations ("
            "name text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        conn.commit()
        done = {r["name"] for r in conn.execute("SELECT name FROM public.schema_migrations")}
        for path in _files():
            if path.name in done:
                continue
            sql = path.read_text(encoding="utf-8")
            with conn.transaction():
                conn.execute(sql)  # type: ignore[arg-type]
                conn.execute(
                    "INSERT INTO public.schema_migrations (name, sha256) VALUES (%s, %s)",
                    (path.name, hashlib.sha256(sql.encode()).hexdigest()),
                )
            applied_now.append(path.name)
        conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_ID,))
        conn.commit()
    return applied_now


if __name__ == "__main__":
    names = run_migrations()
    print(f"applied {len(names)} migration(s): {', '.join(names) or 'none (up to date)'}")
