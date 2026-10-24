"""Integration: print a one-time Telegram /start code for a demo person.

    python -m cm.jobs.make_invite --patient PT-0142      (token like P-0142 also accepted)

Prints only the code and the command to send. The code is single use and expires in 24 h.
"""

from __future__ import annotations

import argparse
import re
import sys

from cm.core import clock, db
from cm.store import channels_repo


def normalise(token: str) -> str:
    t = token.strip().upper()
    m = re.fullmatch(r"(?:PT|P)-?(\d{2,4})", t)
    return f"P-{m.group(1)}" if m else t


def make(token: str, ttl_hours: int = 24) -> str | None:
    who = channels_repo.person_by_token(normalise(token))
    if not who:
        return None
    return channels_repo.create_invite(who["person_id"], clock.now(), ttl_hours)


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--patient")
    g.add_argument("--person")
    ap.add_argument("--ttl-hours", type=int, default=24)
    a = ap.parse_args()
    code = make(a.patient or a.person, a.ttl_hours)
    db.close_pool()
    if not code:
        print("no such person", file=sys.stderr)
        raise SystemExit(1)
    print(code)
    print(f"Send this to your bot in Telegram:  /start {code}")


if __name__ == "__main__":
    main()
