"""One-time Gmail/Calendar OAuth consent helper (owner runs this once, locally). NOT run by tests or CI.

Usage:
    GMAIL_OAUTH_CLIENT_JSON=<path to the OAuth client file> python scripts/gmail_auth.py

Opens a browser for consent on a loopback port, then prints ONLY instructions: the refresh token is written to
a file you name (default ./gmail_refresh_token.txt, mode 600 where supported) and is never printed. Copy its
contents into the secret store / .env as GMAIL_REFRESH_TOKEN, then delete the file. Never commit it.
Other env names used at runtime: GMAIL_MAILBOX, DOCTOR_EMAIL_ALLOWLIST, GMAIL_PUBSUB_TOPIC,
PUBSUB_PUSH_AUDIENCE, PUBSUB_PUSH_SA_EMAIL, GOOGLE_CALENDAR_ID.
"""

from __future__ import annotations

import argparse
import os
import sys

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.events",
]


def run(client_json: str, out_path: str, port: int) -> int:
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(client_json, SCOPES)
    creds = flow.run_local_server(port=port, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        print("No refresh token returned. Revoke the app's access in your Google account and run again.")
        return 1
    fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(creds.refresh_token)
    print(f"Refresh token written to {out_path}. Put it in GMAIL_REFRESH_TOKEN, then delete the file.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="gmail_refresh_token.txt")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)
    client = os.environ.get("GMAIL_OAUTH_CLIENT_JSON")
    if not client:
        print("Set GMAIL_OAUTH_CLIENT_JSON to the path of your OAuth client file.")
        return 2
    return run(client, args.out, args.port)


if __name__ == "__main__":
    sys.exit(main())
