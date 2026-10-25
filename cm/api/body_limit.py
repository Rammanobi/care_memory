"""Lane G: request body cap for upload routes, enforced BEFORE the multipart body is parsed or spooled.

FastAPI parses ``File(...)`` parameters before the route runs, so a size check inside the route only fires after
the whole body was read. This ASGI middleware answers 413 from the declared Content-Length without reading
anything, and for a streamed body (no or lying Content-Length) stops reading once the cap is passed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from cm.api.deps import problem_response

TOO_LARGE_TITLE = "This file is too large. Please send one that is smaller."
FRAMING_SLACK = 64 * 1024  # multipart boundaries and part headers


class BodyLimitMiddleware:
    """413 for POST bodies over ``limit() + FRAMING_SLACK`` on the listed paths (other requests untouched)."""

    def __init__(self, app: ASGIApp, paths: tuple[str, ...], limit: Callable[[], int]) -> None:
        self.app, self.paths, self.limit = app, paths, limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") not in self.paths
        ):
            await self.app(scope, receive, send)
            return
        cap = self.limit() + FRAMING_SLACK
        declared = dict(scope.get("headers") or []).get(b"content-length", b"").decode("latin-1")
        if declared.isdigit() and int(declared) > cap:
            await _too_large(scope, receive, send)
            return
        state: dict[str, Any] = {"seen": 0, "over": False, "started": False}

        async def capped_receive() -> Message:
            if state["over"]:
                return {"type": "http.disconnect"}
            msg = await receive()
            if msg["type"] == "http.request":
                state["seen"] += len(msg.get("body", b""))
                if state["seen"] > cap:
                    state["over"] = True  # stop here: the rest of the body is never read
                    return {"type": "http.disconnect"}
            return msg

        async def guarded_send(msg: Message) -> None:
            if state["over"]:
                if msg["type"] == "http.response.start" and not state["started"]:
                    state["started"] = True
                    await _too_large(scope, receive, send)
                return  # the app's own reply to the cut-off body is replaced by the 413
            await send(msg)

        try:
            await self.app(scope, capped_receive, guarded_send)
        except Exception:
            if not state["over"]:
                raise
        if state["over"] and not state["started"]:  # the app gave up on the body without replying
            state["started"] = True
            await _too_large(scope, receive, send)


async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
    await problem_response(413, TOO_LARGE_TITLE, "too_large")(scope, receive, send)
