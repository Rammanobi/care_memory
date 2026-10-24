import json
from datetime import date
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from cm.agents.context import RunContext
from cm.agents.orchestrator import build_orchestrator, run
from cm.memory.features import compute_features
from tests.unit.ai.conftest import AS_OF, PID, FakeChat


def call(name, args, i):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{i}"}])


def make(events, narrator_reply=None):
    f = compute_features(events, AS_OF, day0=date(2026, 8, 27))
    c = f.cites["missed_7d"][0]
    reply = narrator_reply or json.dumps({"sentences": [f"Missed 2 doses in the last 7 days [{c}]."]})
    ctx = RunContext(PID, "P-0142", AS_OF, "nightly-P-0142-d59", "nightly_patient:P-0142:59:abcd1234", events, f,
                     model=FakeChat(script=[reply]))
    created = []

    def writer(**kw):
        created.append(kw)
        return uuid4()

    script = [
        call("write_todos", {"todos": [{"content": "read", "status": "in_progress"},
                                       {"content": "card", "status": "pending"}]}, 1),
        call("get_patient_snapshot", {}, 2), call("compute_features", {}, 3),
        call("list_events", {"limit": 5}, 4), call("write_card", {}, 5),
        call("submit_for_review", {"card_id": "card-1"}, 6),
        AIMessage(content="amber, 1 sentence"),
    ]
    agent = build_orchestrator(FakeChat(script=script), ctx, checkpointer=MemorySaver(), write_approval=writer)
    return agent, ctx, created


def test_todos_tools_interrupt_resume(events):
    agent, ctx, created = make(events)
    out = run(agent, ctx)
    assert out["status"] == "interrupted"
    assert [t["content"] for t in out["todos"]] == ["read", "card"]
    assert ctx.tool_calls == ["get_patient_snapshot", "compute_features", "list_events", "write_card"]
    assert created == []  # nothing is created before the interrupt is answered
    out = run(agent, ctx, resume="approve")
    assert out["status"] == "done" and ctx.tool_calls[-1] == "submit_for_review"
    assert len(created) == 1 and created[0]["tier"] == "amber" and created[0]["payload"]["audience"] == "doctor"
    assert created[0]["payload"]["sentences"][0]["refs"]


def test_reject_creates_nothing(events):
    agent, ctx, created = make(events)
    run(agent, ctx)
    run(agent, ctx, resume="reject")
    assert created == [] and ctx.approvals == []


def test_bad_card_cannot_be_submitted(events):
    agent, ctx, created = make(events)
    run(agent, ctx)
    ctx.cards["card-1"]["card"].sentences.append("Invented claim with no citation.")
    with pytest.raises(Exception):
        run(agent, ctx, resume="approve")
    assert created == []
