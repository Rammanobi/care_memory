"""Offline stand-ins used by `nightly` without --live (no network, no key)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedChat(BaseChatModel):
    """Returns queued messages in order (last repeats). bind_tools is a no-op."""

    script: list[Any] = []
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kw: Any) -> Any:
        return self

    def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kw: Any) -> ChatResult:
        m = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=m if isinstance(m, AIMessage) else AIMessage(content=m))])


def _call(name: str, args: dict[str, Any], i: int) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{i}"}])


def fake_agent_model() -> ScriptedChat:
    todos = [{"content": "Read facts", "status": "in_progress"}, {"content": "Write and submit card", "status": "pending"}]
    return ScriptedChat(script=[
        _call("write_todos", {"todos": todos}, 1), _call("get_patient_snapshot", {}, 2),
        _call("compute_features", {}, 3), _call("list_events", {"limit": 15}, 4), _call("write_card", {}, 5),
        _call("submit_for_review", {"card_id": "card-1"}, 6), AIMessage(content="Card submitted for review."),
    ])


def fake_narrator(cites: dict[str, list[str]]) -> ScriptedChat:
    """Narrator reply built only from real citation ids (so offline runs exercise cite-or-cut)."""
    key = "missed_7d" if cites.get("missed_7d") else "taken_7d"
    c = (cites.get(key) or ["B-longest_streak"])[0]
    return ScriptedChat(script=[json.dumps({"sentences": [f"Offline draft: see the recent check-ins [{c}]."]})])
