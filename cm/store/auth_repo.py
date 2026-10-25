"""Login credential maintenance (the only place outside migrations that writes cm.auth_credentials flags)."""

from __future__ import annotations

from typing import Any

from cm.core.db import transaction


def disable_login(usernames: list[str], *, conn: Any = None) -> int:
    """Disable logins and bump token_version so live sessions die. Idempotent; unknown users are skipped.

    Returns how many logins were newly disabled. Never deletes rows.
    """
    if conn is None:
        with transaction() as c:
            return disable_login(usernames, conn=c)
    n = 0
    for u in usernames:
        cur = conn.execute(
            "UPDATE cm.auth_credentials SET active=false, token_version=token_version+1 "
            "WHERE username=%s AND active",
            (u,),
        )
        n += cur.rowcount
    return n
