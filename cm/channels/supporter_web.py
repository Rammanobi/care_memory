"""Lane F: Supporter web helper functions (no UI). Supporter wording never contains disease or drug words."""

from __future__ import annotations

from typing import Any

from cm.router.banned import find_banned

NO_VISITS = "No visits needed today."
VISIT_BUTTONS = ["Visited - saw dose", "Visited - was told", "Couldn't reach", "Why?"]


def render_visit_list(items: list[dict[str, Any]], max_items: int = 6) -> list[str]:
    """Approved items only, in rank order, capped. Each line passes the banned-term check or is dropped."""
    ok = [i for i in items if i.get("status") in ("approved", "edited")]
    ok.sort(key=lambda i: i.get("rank", 99))
    lines = []
    for n, i in enumerate(ok[:max_items], 1):
        line = f"{n}. {i['name']} ({i.get('place', '')}): please check in and count the tablets.".replace(
            " ()", ""
        )
        if not find_banned(line):
            lines.append(line)
    return lines or [NO_VISITS]


def supporter_text_ok(text: str) -> bool:
    return not find_banned(text)


def visit_to_event(mode: str, pill_count: int | None = None) -> dict[str, Any]:
    """Map a visit mode to reporter_mode and implied dose status (witnessed -> taken, told -> taken, else unclear)."""
    if mode not in ("witnessed", "told", "unreachable"):
        raise ValueError("bad visit mode")
    if pill_count is not None and not 0 <= pill_count <= 120:
        raise ValueError("pill_count out of range")
    return {
        "reporter_mode": mode if mode != "unreachable" else "told",
        "implied_dose": {"witnessed": "taken", "told": "taken"}.get(mode, "unclear"),
        "pill_count": pill_count,
    }
