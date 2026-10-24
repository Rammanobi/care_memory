import pytest
from langchain_core.messages import AIMessage

from cm.core import budget as b
from cm.core.llm import GovernedModel
from cm.tools.readonly import BannedTermError, governed
from tests.unit.ai.conftest import AS_OF, PID

ENV = {"ORCHESTRATOR_MODEL": "deepseek:pro", "WORKER_MODEL": "deepseek:flash", "CM_DATA_CLASS": "mock"}


class Fake:
    def __init__(self, name):
        self.name = name

    def invoke(self, m, **kw):
        return AIMessage(content=self.name, usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})


def gov(spent):
    store = b.InMemoryUsageStore()
    g = b.BudgetGovernor(b.BudgetLimits(daily_usd=10, demo_reserve_usd=0), b.PriceTable(), store)
    if spent:
        store.add(day=g.today(), task_id="x", task_type="eval", patient_id=None, tokens_in=0, tokens_out=0, cost_usd=spent)
    return g


def model(g):
    return GovernedModel("ORCHESTRATOR", governor=g, env=ENV, builder=lambda spec, role: Fake(spec))


def test_green_amber_red():
    assert model(gov(0)).invoke("hi").content == "deepseek:pro"
    assert model(gov(8.0)).invoke("hi").content == "deepseek:flash"  # AMBER (70-90%) -> worker
    with pytest.raises(b.TemplateOnlyMode):
        model(gov(9.9)).invoke("hi")


def test_pii_blocked_and_usage_recorded():
    g = gov(0)
    model(g).invoke("hello", task_id="t1", task_type="nightly_patient")
    assert g.store.task_cost("t1") > 0
    from cm.core.tokenize import PIILeak

    with pytest.raises(PIILeak):
        model(g).invoke("call 9876543210")


def test_patient_facing_tool_blocks_banned_terms():
    class Ctx:
        breaker = None
        tool_calls: list = []

    f = governed(Ctx, "t", lambda: {"text": "take rifampicin"}, patient_facing=True)
    with pytest.raises(BannedTermError):
        f()
    assert governed(Ctx, "t", lambda: {"text": "hello"}, patient_facing=True)()
