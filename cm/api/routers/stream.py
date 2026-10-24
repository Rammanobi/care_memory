"""Lane G: GET /stream, Server-Sent Events fed by Postgres LISTEN/NOTIFY (migration 0008).

Event name = topic (review, channels) because web/src/realtime/sse.ts listens by topic name; the JSON
data carries the precise type: approval_created, approval_decided, request_created, message_sent.
A comment line ": ping" is sent every 15 s. Auth is the session cookie (or bearer header).
"""
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

import json
import time
from collections.abc import Iterator

import psycopg
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from cm.api.deps import User, current_user
from cm.core.config import load_settings

router = APIRouter(tags=["stream"])
HEARTBEAT_S = 15.0
CHANNEL = "cm_events"


def _visible(user: User, ev: dict[str, str | None]) -> bool:
    if user.role in ("doctor", "admin"):
        return True
    return ev.get("person_id") == str(user.person_id)  # patients and Supporters: only their own


def event_iter(
    user: User, topics: set[str], heartbeat_s: float = HEARTBEAT_S, tick_s: float = 1.0
) -> Iterator[str]:
    """Yield SSE text frames until the caller stops iterating."""
    conn = psycopg.connect(load_settings().dsn, autocommit=True)
    try:
        conn.execute(f"LISTEN {CHANNEL}")
        yield "retry: 3000\n: connected\n\n"
        last = time.monotonic()
        while True:
            got = False
            for n in conn.notifies(timeout=tick_s, stop_after=50):
                got = True
                ev = json.loads(n.payload)
                if (not topics or ev["topic"] in topics) and _visible(user, ev):
                    data = json.dumps({k: v for k, v in ev.items() if k != "person_id"})
                    yield f"event: {ev['topic']}\ndata: {data}\n\n"
                    last = time.monotonic()
            if not got and time.monotonic() - last >= heartbeat_s:
                yield ": ping\n\n"
                last = time.monotonic()
    finally:
        conn.close()


@router.get("/stream")
def stream(topics: str = "", user: User = Depends(current_user)) -> StreamingResponse:
    wanted = {t for t in topics.split(",") if t}
    return StreamingResponse(
        event_iter(user, wanted),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
