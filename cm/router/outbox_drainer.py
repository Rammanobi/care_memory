"""Lane F (Telegram, Supporter, router) — see INTEGRATION_DECISIONS.md §e (drainer throttle).

Skeleton only. Business logic is not implemented yet.
"""

from typing import Any


class OutboxDrainer:
    """Drains the outbox with throttle."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError
