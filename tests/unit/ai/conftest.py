from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

AS_OF = datetime(2026, 10, 24, 12, 30, tzinfo=UTC)  # Saturday 18:00 IST
PID = UUID("2f3e2a8a-2986-5670-9494-5ce15e2c87d0")


def ev(type_, days_ago, payload, source="web", **kw):
    t = AS_OF - timedelta(days=days_ago, hours=10)
    return {"event_id": kw.pop("event_id", uuid4()), "patient_id": PID, "type": type_, "occurred_at": t,
            "recorded_at": t, "source": source, "payload": payload, **kw}


@pytest.fixture()
def events():
    out = []
    for d in range(20, -1, -1):  # 21 days, misses 1, 3, 8, 15 days ago
        out.append(ev("DoseCheckin", d, {"status": "missed" if d in (1, 3, 8, 15) else "taken"}))
    out.append(ev("Dispense", 2, {"why": "Supply for 14 days ran out around day 47", "text": "No refill since day 33"},
                  source="chemist"))
    return out


class FakeChat(BaseChatModel):
    """Scripted chat model: returns queued messages in order (last one repeats); bind_tools is a no-op."""

    script: list = []
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools, **kw):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kw):
        m = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=m if isinstance(m, AIMessage) else AIMessage(content=m))])
