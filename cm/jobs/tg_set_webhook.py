"""Integration: register or delete the Telegram webhook. Prints success or failure only.

    python -m cm.jobs.tg_set_webhook            # PUBLIC_BASE_URL/webhooks/telegram + secret header value
    python -m cm.jobs.tg_set_webhook --delete

Token and secret come from the environment / .env and are never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from cm.channels.tg_client import TgError
from cm.channels.tg_http import admin_call
from cm.core.config import load_dotenv


async def run(delete: bool) -> str:
    if delete:
        await admin_call("deleteWebhook", {"drop_pending_updates": False})
        return "webhook deleted"
    base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if not base.startswith("https://"):
        raise ValueError("PUBLIC_BASE_URL must be an https URL (your ngrok URL)")
    if not secret:
        raise ValueError("TELEGRAM_WEBHOOK_SECRET is not set")
    await admin_call(
        "setWebhook",
        {
            "url": f"{base}/webhooks/telegram",
            "secret_token": secret,
            "allowed_updates": ["message", "callback_query"],
        },
    )
    return f"webhook set to {base}/webhooks/telegram"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delete", action="store_true")
    a = ap.parse_args()
    load_dotenv()
    try:
        print("OK:", asyncio.run(run(a.delete)))
        return 0
    except (TgError, ValueError) as exc:
        print("FAILED:", type(exc).__name__, str(exc))  # messages never contain the token
        return 1


if __name__ == "__main__":
    sys.exit(main())
