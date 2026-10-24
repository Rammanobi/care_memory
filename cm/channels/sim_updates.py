"""Lane F: builders for fake Telegram updates (tests and local simulation). No network."""

from __future__ import annotations

from typing import Any


def _user(chat_id: int) -> dict[str, Any]:
    return {"id": chat_id, "is_bot": False, "first_name": "Sim"}


def message(update_id: int, chat_id: int, text: str, chat_type: str = "private") -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 0,
            "text": text,
            "chat": {"id": chat_id, "type": chat_type},
            "from": _user(chat_id),
        },
    }


def start(update_id: int, chat_id: int, code: str) -> dict[str, Any]:
    return message(update_id, chat_id, f"/start {code}")


def stop(update_id: int, chat_id: int) -> dict[str, Any]:
    return message(update_id, chat_id, "/stop")


def tap(update_id: int, chat_id: int, data: str, message_id: int = 500) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cq{update_id}",
            "from": _user(chat_id),
            "data": data,
            "message": {"message_id": message_id, "chat": {"id": chat_id, "type": "private"}},
        },
    }


def dose_tap(update_id: int, chat_id: int, prompt_hex: str, code: str) -> dict[str, Any]:
    """code: t taken, m missed, u unwell."""
    return tap(update_id, chat_id, f"c:{prompt_hex}:{code}")


def symptom_tap(
    update_id: int, chat_id: int, prompt_hex: str, mask: int, last: str
) -> dict[str, Any]:
    return tap(update_id, chat_id, f"s:{prompt_hex}:{mask:02x}:{last}")
