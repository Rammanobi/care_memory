"""Lane E (Runtime, gate, tools) — see CAREMEMORY_ARCHITECTURE.md §3.14.

Skeleton only. Business logic is not implemented yet.
"""

from typing import Any


def register_tool(fn: Any) -> Any:
    """Register a typed tool."""
    raise NotImplementedError


def tools_for_role(role: str) -> list[Any]:
    """Tools visible to a role."""
    raise NotImplementedError
