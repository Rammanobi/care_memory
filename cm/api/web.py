"""Production web serving: Host validation and the built web app (SPA) served by the API.

The same image works on any hostname: the web bundle calls a relative API base, the API serves the
bundle. Everything is driven by env (names only): CM_ALLOWED_HOSTS, CM_WEB_DIR. API routes are
registered first, so the SPA catch-all is last and never shadows them.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

HOST_EXEMPT = ("/healthz", "/readyz")  # probes arrive with internal Host headers
IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"


def parse_hosts(raw: str | None) -> tuple[str, ...]:
    """Comma list of host names (no scheme, no port). '*.example.com' matches subdomains."""
    return tuple(h.strip().lower() for h in (raw or "").split(",") if h.strip())


def host_allowed(host: str, allowed: tuple[str, ...]) -> bool:
    if not allowed or "*" in allowed:
        return True
    name = host.strip().lower()
    name = name.split("]")[0] + "]" if name.startswith("[") else name.split(":")[0]  # [::1]:8080
    for pat in allowed:
        if name == pat or (pat.startswith("*.") and name.endswith(pat[1:]) and name != pat[2:]):
            return True
    return False


class AllowedHostsMiddleware:
    """Reject requests whose Host header is not in CM_ALLOWED_HOSTS (empty list = allow all)."""

    def __init__(self, app: ASGIApp, allowed: tuple[str, ...]) -> None:
        self.app = app
        self.allowed = allowed

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        checked = scope["type"] in ("http", "websocket") and scope.get("path") not in HOST_EXEMPT
        if checked and self.allowed:
            host = dict(scope.get("headers") or []).get(b"host", b"").decode("latin-1")
            if not host_allowed(host, self.allowed):
                if scope["type"] == "http":
                    await Response("Invalid host header", status_code=400)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def web_dir() -> Path | None:
    """Built web app directory (CM_WEB_DIR, default web/dist); None when it is not there."""
    root = Path(
        os.environ.get("CM_WEB_DIR") or Path(__file__).resolve().parents[2] / "web" / "dist"
    )
    return root if (root / "index.html").is_file() else None


def mount_spa(app: FastAPI, root: Path | None = None) -> bool:
    """Register the static + SPA fallback route. Call after every API router."""
    root = root or web_dir()
    if root is None:
        return False
    base = root.resolve()
    index = base / "index.html"

    def _file(p: Path) -> FileResponse:
        cache = IMMUTABLE if "assets" in p.relative_to(base).parts else REVALIDATE
        return FileResponse(p, headers={"Cache-Control": cache})

    @app.get("/{full_path:path}", include_in_schema=False)
    @app.head("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str, request: Request) -> Response:
        target = (base / full_path).resolve() if full_path else index
        if full_path and target.is_file() and base in target.parents:
            return _file(target)
        accept = request.headers.get("accept", "")
        wants_html = "text/html" in accept or "application/json" not in accept  # curl sends */*
        if wants_html and "." not in full_path.rsplit("/", 1)[-1]:
            return _file(index)  # client-side route: /doctor, /patient/..., /supporter
        return JSONResponse(
            {"title": "Not found", "code": "http_error", "status": 404}, status_code=404
        )

    return True
