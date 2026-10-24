"""Integration: AI budget numbers for the admin usage-and-caps panel (GET /admin/usage/caps)."""
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cm.api.deps import User, require_roles
from cm.core import budget, llm

router = APIRouter(prefix="/admin", tags=["admin"])


class CapsAlert(BaseModel):
    level: str  # AMBER | RED
    kind: str  # budget_70 | budget_90 | spend_cap_402
    title: str
    body: str
    pct: float


class UsageCapsWithAlerts(budget.UsageCapsPanel):
    alerts: list[CapsAlert] = []


def current_alerts(panel: budget.UsageCapsPanel) -> list[CapsAlert]:
    """Read-only view of the owner alerts for the current state (does not consume the once-per-day send)."""
    out: list[CapsAlert] = []
    if panel.billing_error:
        out.append(CapsAlert(level="RED", kind="spend_cap_402", title="AI provider credits exhausted",
                             body="Template-only mode is on. Top up credits.", pct=panel.today_pct))
    if panel.today_pct / 100 > budget.RED_ABOVE:
        out.append(CapsAlert(level="RED", kind="budget_90", title="AI budget over 90% today",
                             body="Template-only mode is active.", pct=panel.today_pct))
    elif panel.today_pct / 100 >= budget.AMBER_AT:
        out.append(CapsAlert(level="AMBER", kind="budget_70", title="AI budget at 70% today",
                             body="Cheaper model and shorter drafts are in use.", pct=panel.today_pct))
    return out


@router.get("/usage/caps", response_model=UsageCapsWithAlerts)
def usage_caps(_: User = Depends(require_roles("doctor", "admin"))) -> UsageCapsWithAlerts:
    panel = budget.usage_numbers(llm.get_governor(), llm.get_limiter().utilisation() * 100)
    return UsageCapsWithAlerts(**panel.model_dump(), alerts=current_alerts(panel))
