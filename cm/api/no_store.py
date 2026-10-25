"""Lane G: ``Cache-Control: private, no-store`` on authenticated API responses (Firebase Hosting CDN safety).

Pure ASGI (no response buffering, so SSE streams are unaffected). A request counts as authenticated when it
carries an ``Authorization`` header or the ``cm_session`` cookie. A response that already sets its own
``Cache-Control`` (e.g. static assets) is left alone.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

NO_STORE = "private, no-store"


class NoStoreMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        authed = b"authorization" in headers or b"cm_session=" in headers.get(b"cookie", b"")

        async def _send(message: Message) -> None:
            if authed and message["type"] == "http.response.start":
                h = MutableHeaders(scope=message)
                if "cache-control" not in h:
                    h["Cache-Control"] = NO_STORE
            await send(message)

        await self.app(scope, receive, _send)
