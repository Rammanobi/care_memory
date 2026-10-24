"""Lane G: publish a live event on the same LISTEN/NOTIFY channel that feeds GET /stream.

The migration triggers (0008) publish row events. This helper publishes application events (for example
a patient question that is ready for the doctor). The payload carries ids and short labels only, never
patient text. ``person_id`` is left empty so only doctors and admins receive it (see stream._visible).
"""

from __future__ import annotations

import json
from typing import Any

from cm.core.db import transaction

CHANNEL = "cm_events"
MAX_BYTES = 7000  # pg_notify limit is 8000 bytes


def publish(topic: str, event: dict[str, Any], *, conn: Any = None) -> None:
    """NOTIFY ``cm_events`` with {topic, ...event}. Delivered on commit of the surrounding transaction."""
    body = json.dumps({"topic": topic, **event}, default=str)
    if len(body.encode()) > MAX_BYTES:
        raise ValueError("stream event too large")
    if conn is None:
        with transaction() as c:
            return publish(topic, event, conn=c)
    conn.execute("SELECT pg_notify(%s, %s)", (CHANNEL, body))
