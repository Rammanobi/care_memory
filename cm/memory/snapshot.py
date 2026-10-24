"""Lane C (Memory engine) — see INTEGRATION_DECISIONS.md §a4 M7 (P1).

Skeleton only. Business logic is not implemented yet.
"""

from collections.abc import Sequence
from typing import Any


def snapshot(pid: Any, day: int, exclude_sources: Sequence[str] = ()) -> Any:
    """One-patient snapshot (what-if is P1)."""
    raise NotImplementedError
