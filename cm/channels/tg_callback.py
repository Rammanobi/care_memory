"""Lane F: build and parse callback_data (<= 64 bytes).

Formats: c:{p}:t|m|u  s:{p}:{mask hex}:{i|d|n}  stop:{p}:d|a|x  pay:{p}:y|n|u
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from cm.contracts.api import TgCallback

SYMPTOMS = [
    "Cough worse",
    "Fever",
    "Night sweats",
    "Poor appetite or weight loss",
    "Nausea or vomiting",
    "Yellow eyes or skin",
    "Blood when coughing",
    "Hard to breathe",
]
DANGER_INDEXES = frozenset({5, 6, 7})
DOSE_CODE = {"t": "taken", "m": "missed", "u": "unwell"}


def parse(data: str | None) -> TgCallback | None:
    """Parse callback_data; None when malformed."""
    if not data or len(data.encode()) > 64:
        return None
    parts = data.split(":")
    try:
        kind = parts[0]
        if kind in ("c", "stop", "pay") and len(parts) == 3:
            return TgCallback(kind=kind, prompt=parts[1], value=parts[2])
        if kind == "s" and len(parts) == 4:
            mask = int(parts[2], 16)
            if not 0 <= mask <= 255:
                return None
            last = parts[3]
            if last in ("d", "n"):
                return TgCallback(kind="s", prompt=parts[1], mask=mask, value=last)
            idx = int(last)
            if not 0 <= idx <= 7:
                return None
            return TgCallback(kind="s", prompt=parts[1], mask=mask, index=idx, value="t")
    except (ValueError, ValidationError):
        return None
    return None


def dose_buttons(p: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Taken", "callback_data": f"c:{p}:t"},
                {"text": "Missed", "callback_data": f"c:{p}:m"},
                {"text": "Feeling unwell", "callback_data": f"c:{p}:u"},
            ]
        ]
    }


def symptom_keyboard(p: str, mask: int) -> dict[str, Any]:
    rows = []
    for i, label in enumerate(SYMPTOMS):
        mark = "[x] " if mask & (1 << i) else ""
        rows.append([{"text": mark + label, "callback_data": f"s:{p}:{mask:02x}:{i}"}])
    rows.append(
        [
            {"text": "Done", "callback_data": f"s:{p}:{mask:02x}:d"},
            {"text": "None", "callback_data": f"s:{p}:00:n"},
        ]
    )
    return {"inline_keyboard": rows}


def mask_items(mask: int) -> list[int]:
    return [i for i in range(8) if mask & (1 << i)]
