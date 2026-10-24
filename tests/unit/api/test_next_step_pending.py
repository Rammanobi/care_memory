"""Patients list next step: never 'Approved and sent' while a draft is still pending."""

from cm.api.readmodels import _level


def _item(status: str, tier: str = "amber", green: bool = False) -> dict[str, object]:
    return {"status": status, "tier": tier, "is_req": False, "green": green}


def test_approved_and_sent_only_when_nothing_pending() -> None:
    assert _level("amb", "WATCH", "Call", [_item("approved")])[2] == "Approved and sent"


def test_pending_green_draft_blocks_approved_and_sent() -> None:
    items = [_item("approved"), _item("pending", "green", green=True)]
    level, _, nxt, needs, _ = _level("amb", "WATCH", "Call", items)
    assert nxt == "Call" and not needs and level == "amb"


def test_pending_doctor_draft_blocks_it_too() -> None:
    assert _level("amb", "WATCH", "Call", [_item("approved"), _item("pending")])[2] == "Call"
