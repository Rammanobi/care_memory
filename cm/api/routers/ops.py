"""Integration: AI budget numbers for the admin usage-and-caps panel (GET /admin/usage/caps)."""
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

from fastapi import APIRouter, Depends

from cm.api.deps import User, require_roles
from cm.core import budget, llm

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/usage/caps", response_model=budget.UsageCapsPanel)
def usage_caps(_: User = Depends(require_roles("doctor", "admin"))) -> budget.UsageCapsPanel:
    return budget.usage_numbers(llm.get_governor(), llm.get_limiter().utilisation() * 100)
