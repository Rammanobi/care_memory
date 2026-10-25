"""Set a demo login password you choose (local use). Usage: python scripts/reset_demo_password.py dr.rao

Asks for the new password with no echo; nothing is printed or stored in a file. Bumps token_version so old sessions end.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cm.api.auth import hash_password
from cm.core.db import transaction


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts/reset_demo_password.py <username>")
        return 2
    user = sys.argv[1]
    pw = getpass.getpass(f"New password for {user}: ")
    if len(pw) < 8 or pw != getpass.getpass("Type it again: "):
        print("Not changed: use at least 8 characters and type the same twice.")
        return 1
    with transaction() as c:
        n = c.execute(
            "UPDATE cm.auth_credentials SET password_hash=%s, token_version=token_version+1 "
            "WHERE username=%s AND active",
            (hash_password(pw), user),
        ).rowcount
    print("Password changed." if n else "No active account with that username.")
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
