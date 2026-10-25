"""Collect every demo login into one git-ignored file: `python scripts/make_demo_env.py`.

Reads (never prints): .env (DEMO_USER_PASSWORDS for the doctor/admin/original demo users) and
out/demo_accounts_credentials.txt (demo patients PT-0906 and PT-0960, written by
`python -m cm.jobs.seed_demo_accounts`). Writes `.env.demo` (ignored by git through `.env.*`), one
KEY=value line per account, so you can keep it next to .env or move it to a password manager.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".env.demo"

ROLES = {
    "dr.rao": ("DOCTOR", "doctor console"),
    "admin.demo": ("ADMIN", "admin"),
    "ravi.pt0142": ("PATIENT_PT0142", "60 days, Telegram-bound demo patient"),
    "lakshmi.s01": ("SUPPORTER_PT0142", "Supporter of PT-0142"),
    "demo.pt0906": ("PATIENT_PT0906_6DAY", "6 days of data"),
    "demo.pt0960": ("PATIENT_PT0960_60DAY", "60 days of data"),
}


def read_pairs() -> dict[str, str]:
    pairs: dict[str, str] = {}
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEMO_USER_PASSWORDS="):
                raw = line.split("=", 1)[1].strip().strip("'\"")
                try:  # current format: a JSON object {"user": "password", ...}
                    pairs.update({str(u): str(p) for u, p in json.loads(raw).items()})
                except (ValueError, AttributeError):  # older format: user:password,user:password
                    for part in raw.split(","):
                        if ":" in part:
                            u, p = part.split(":", 1)
                            pairs[u.strip()] = p.strip()
    cred = ROOT / "out" / "demo_accounts_credentials.txt"
    if cred.exists():
        for line in cred.read_text(encoding="utf-8").splitlines():
            if "\t" in line:
                u, p = line.split("\t", 1)
                pairs[u.strip()] = p.strip()
    return pairs


def main() -> None:
    pairs = read_pairs()
    lines = ["# Demo logins (mock data only). Git-ignored. Do not commit or share.", ""]
    for user, (key, note) in ROLES.items():
        if user in pairs:
            lines += [f"# {note}", f"DEMO_{key}_USER={user}", f"DEMO_{key}_PASSWORD={pairs[user]}", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT.name} with {sum(1 for u in ROLES if u in pairs)} of {len(ROLES)} accounts (values not printed)")


if __name__ == "__main__":
    main()
