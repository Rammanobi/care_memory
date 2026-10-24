"""Lane G: POST /webhooks/telegram. Verifies the secret header, saves the event, replies inline.

The Bot API accepts a method call as the JSON response body, so the reply (answerCallbackQuery,
sendMessage, editMessageReplyMarkup) goes back in the ack with no outbound call: well under 1 s.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from cm.channels.adapters_pg import build_deps
from cm.channels.telegram import handle_webhook
from cm.core.logging import get_logger

router = APIRouter(tags=["webhooks"])
log = get_logger()
HEADER = "X-Telegram-Bot-Api-Secret-Token"


def _handle(raw: dict[str, Any], secret: str | None) -> tuple[int, dict[str, Any]]:
    return handle_webhook(raw, secret, build_deps())


@router.post("/webhooks/telegram")
async def telegram_webhook(request: Request) -> JSONResponse:
    secret = request.headers.get(HEADER)
    try:
        raw = await request.json()
    except ValueError:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    try:
        status, body = await run_in_threadpool(_handle, raw, secret)
    except Exception as exc:  # never let Telegram see a 5xx loop; the event is retried by update id
        log.warning("telegram webhook error", error=type(exc).__name__)
        return JSONResponse(status_code=200, content={"ok": True})
    return JSONResponse(status_code=status, content=body)
