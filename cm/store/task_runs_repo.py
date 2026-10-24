"""Lane A (Data core) — see INTEGRATION_DECISIONS.md §a2 T10 and Z2.

Skeleton only. Business logic is not implemented yet.
"""

from typing import Any


def claim(task_id: str) -> Any:
    """Move a task to running; None if done."""
    raise NotImplementedError


def heartbeat(task_id: str) -> None:
    """Update heartbeat_at."""
    raise NotImplementedError
