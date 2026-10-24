"""CareMemory frozen contracts (``contracts-v1``).

Tier 1: ``domain``, ``memory``, ``review``, ``agents``, ``api``, ``tools``.
Tier 2: ``dashboard``, ``admin``, ``evalsim``.

Never edit these files in a build lane. Request changes in ``contracts/CHANGES.md``.
SQL counterpart: ``cm/store/migrations/*.sql``. Route list: ``openapi_routes.md``.
"""

from __future__ import annotations

CONTRACTS_VERSION = "contracts-v1"

from . import admin, agents, api, dashboard, domain, evalsim, memory, review, tools  # noqa: E402

__all__ = [
    "CONTRACTS_VERSION", "admin", "agents", "api", "dashboard", "domain", "evalsim", "memory", "review", "tools",
]
