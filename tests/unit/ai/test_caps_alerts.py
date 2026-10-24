"""AMBER/RED alerts shown on GET /admin/usage/caps (read-only, no send)."""

from cm.api.routers.ops import current_alerts
from cm.core.budget import UsageCapsPanel


def _panel(pct: float, billing: bool = False) -> UsageCapsPanel:
    return UsageCapsPanel(state="X", today_spent_usd=0, today_cap_usd=1, today_pct=pct, reserve_locked_usd=0,
                          event_spent_usd=0, event_budget_usd=1, provider_limit_pct=0, spend_by_task_type={},
                          safety_stops=0, billing_error=billing)


def test_green_has_no_alerts():
    assert current_alerts(_panel(40)) == []


def test_amber_at_70():
    assert [a.level for a in current_alerts(_panel(75))] == ["AMBER"]


def test_red_over_90_and_billing():
    assert [a.level for a in current_alerts(_panel(95))] == ["RED"]
    assert [a.kind for a in current_alerts(_panel(10, billing=True))] == ["spend_cap_402"]
