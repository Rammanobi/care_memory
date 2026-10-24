"""Lane C (Memory engine) — see INTEGRATION_DECISIONS.md §a4 M1.

Skeleton only. Business logic is not implemented yet.
"""

from collections.abc import Sequence
from typing import Any


def run_in_memory(events: Any, consents: Any, as_of_days: Sequence[int], *, exclude_sources: Sequence[str] = ()) -> Any:
    """Pure in-memory engine run."""
    raise NotImplementedError
