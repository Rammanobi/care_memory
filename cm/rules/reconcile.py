"""Lane D (Rules, validator, identity) — see INTEGRATION_DECISIONS.md §a4 M3.

Skeleton only. Business logic is not implemented yet.
"""

from datetime import date
from typing import Any


def reconcile_frame(events: Any, patient: Any, as_of: date, thresholds: Any) -> list[Any]:
    """Pure reconcile over a DataFrame."""
    raise NotImplementedError


def reconcile(pid: Any, as_of: date) -> list[Any]:
    """Load and reconcile one patient."""
    raise NotImplementedError
