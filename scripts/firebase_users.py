"""Create/import the demo users into Firebase Auth with custom claims role/pid/tv (FIREBASE_PLAN.md 2.6).

    python scripts/firebase_users.py                       # DRY RUN (default): prints the plan, no network
    python scripts/firebase_users.py --apply               # really create/update (owner machine, ADC)
    python scripts/firebase_users.py --revoke demo.pt0960  # dry run of a revoke; add --apply to do it
    python scripts/firebase_users.py --tv-file out/tv.json # {"dr.rao": 2, ...} if token_version was bumped

The accounts are the SAME demo accounts the seeds create (cm.jobs.seed.USERS + cm.jobs.seed_demo_accounts
.ACCOUNTS); person ids are the deterministic det_id("person", token), so no database read is needed.
Dry run makes no network call and needs no credentials. --apply needs `firebase-admin` (dev only, never in the
API image), Application Default Credentials and FIREBASE_PROJECT_ID; passwords are read only from the JSON env
vars DEMO_USER_PASSWORDS / DEMO_ACCOUNT_PASSWORDS, kept in memory, never printed or written. A password
under 12 characters is refused. Output is one line per user: `username: <action>`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MIN_PASSWORD = 12
PASSWORD_ENVS = ("DEMO_USER_PASSWORDS", "DEMO_ACCOUNT_PASSWORDS")


@dataclass(frozen=True)
class DemoUser:
    username: str
    token: str
    role: str
    pid: str
    tv: int

    def email(self, domain: str) -> str:
        return f"{self.username}@{domain}"

    @property
    def uid(self) -> str:  # stable Firebase uid, independent of the email
        return "cm-" + self.username.replace(".", "-")

    @property
    def claims(self) -> dict[str, Any]:
        return {"role": self.role, "pid": self.pid, "tv": self.tv}


def demo_users(tv: dict[str, int] | None = None) -> list[DemoUser]:
    """The seeded demo accounts (main seed + the 6/60-day accounts)."""
    from cm.core.ids import det_id
    from cm.jobs.seed import USERS
    from cm.jobs.seed_demo_accounts import ACCOUNTS

    pairs = [(u, tok, role) for u, (tok, role, _name) in USERS.items()]
    pairs += [(a["user"], a["token"], "patient") for a in ACCOUNTS]
    tv = tv or {}
    return [DemoUser(u, tok, role, str(det_id("person", tok)), int(tv.get(u, 1))) for u, tok, role in pairs]


class AdminClient(Protocol):
    def find_uid(self, uid: str) -> bool: ...
    def create(self, uid: str, email: str, password: str) -> None: ...
    def update(self, uid: str, email: str, password: str) -> None: ...
    def set_claims(self, uid: str, claims: dict[str, Any] | None) -> None: ...
    def revoke(self, uid: str) -> None: ...


class FirebaseAdminClient:
    """Real client (firebase-admin, imported lazily). Used only with --apply."""

    def __init__(self, project_id: str) -> None:
        import firebase_admin
        from firebase_admin import auth

        if not firebase_admin._apps:
            firebase_admin.initialize_app(options={"projectId": project_id})
        self._auth = auth

    def find_uid(self, uid: str) -> bool:
        try:
            self._auth.get_user(uid)
            return True
        except self._auth.UserNotFoundError:
            return False

    def create(self, uid: str, email: str, password: str) -> None:
        self._auth.create_user(uid=uid, email=email, password=password, email_verified=True, disabled=False)

    def update(self, uid: str, email: str, password: str) -> None:
        self._auth.update_user(uid, email=email, password=password, email_verified=True, disabled=False)

    def set_claims(self, uid: str, claims: dict[str, Any] | None) -> None:
        self._auth.set_custom_user_claims(uid, claims)

    def revoke(self, uid: str) -> None:
        self._auth.update_user(uid, disabled=True)
        self._auth.revoke_refresh_tokens(uid)


def load_passwords(env: dict[str, str] | os._Environ[str] = os.environ) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in PASSWORD_ENVS:
        raw = env.get(name)
        if raw:
            out.update(json.loads(raw))
    return out


def plan_lines(users: list[DemoUser], domain: str) -> list[str]:
    return [f"{u.username}: would create/update {u.email(domain)} claims role={u.role} tv={u.tv}" for u in users]


def apply_users(users: list[DemoUser], client: AdminClient, passwords: dict[str, str], domain: str) -> list[str]:
    """Idempotent create-or-update + claims. Never returns or logs a password."""
    lines: list[str] = []
    for u in users:
        pw = passwords.get(u.username, "")
        if len(pw) < MIN_PASSWORD:
            lines.append(f"{u.username}: skipped (password missing or under {MIN_PASSWORD} chars)")
            continue
        exists = client.find_uid(u.uid)
        (client.update if exists else client.create)(u.uid, u.email(domain), pw)
        client.set_claims(u.uid, u.claims)
        lines.append(f"{u.username}: {'updated' if exists else 'created'}, claims ok")
    return lines


def revoke_user(user: DemoUser, client: AdminClient | None) -> str:
    if client is None:
        return f"{user.username}: would disable, clear claims and revoke refresh tokens"
    client.set_claims(user.uid, None)
    client.revoke(user.uid)
    return f"{user.username}: revoked"


def main(argv: list[str] | None = None, client: AdminClient | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="really call Firebase (default: dry run)")
    ap.add_argument("--revoke", metavar="USERNAME")
    ap.add_argument("--tv-file", type=Path, help='JSON {"username": token_version} (default 1 = fresh seed)')
    ap.add_argument("--email-domain", default=os.environ.get("AUTH_EMAIL_DOMAIN", "users.carememory.app"))
    args = ap.parse_args(argv)
    tv = json.loads(args.tv_file.read_text(encoding="utf-8")) if args.tv_file else None
    users = demo_users(tv)
    if args.apply and client is None:
        project = os.environ.get("FIREBASE_PROJECT_ID", "").strip()
        if not project:
            print("FIREBASE_PROJECT_ID is not set", file=sys.stderr)
            return 2
        client = FirebaseAdminClient(project)
    live = client if args.apply else None
    if args.revoke:
        match = [u for u in users if u.username == args.revoke]
        if not match:
            print(f"unknown demo user: {args.revoke}", file=sys.stderr)
            return 2
        print(revoke_user(match[0], live))
        return 0
    if live is None:
        print("DRY RUN (no network). Add --apply to create/update users.")
        lines = plan_lines(users, args.email_domain)
    else:
        lines = apply_users(users, live, load_passwords(), args.email_domain)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
