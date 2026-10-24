from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from cm.core import budget as b
from cm.core import llm
from cm.core.retry import (ProviderCallFailed, RateLimiter, RetryPolicy, call_with_fallback,
                           call_with_retry, classify)
from cm.core.tokenize import PIILeak, assert_clean, tokenize


def CLOCK():
    return datetime(2026, 10, 24, 9, tzinfo=timezone.utc)


P = b.PriceTable({"m": (1.0, 1.0)})  # $1 per 1k tokens


def gov(**kw):
    lim = b.BudgetLimits(daily_usd=10, demo_reserve_usd=0, event_usd=1000, per_task_usd=1000, **kw)
    return b.BudgetGovernor(lim, P, clock=CLOCK)


def spend(g, usd):
    g.record(model="m", tokens_in=int(usd * 1000), tokens_out=0)


@pytest.mark.parametrize("usd,state", [(6.9, "GREEN"), (7.0, "AMBER"), (9.0, "AMBER"), (9.01, "RED"), (10, "RED")])
def test_state_transitions(usd, state):
    g = gov()
    spend(g, usd)
    assert g.state().value == state


def test_policy_per_state():
    g = gov()
    assert g.policy().allow_optional_subagents and g.policy().model_tier == "primary"
    spend(g, 8)
    p = g.policy()
    assert p.model_tier == "worker" and not p.allow_optional_subagents and p.max_draft_tokens < 800
    spend(g, 2)
    assert g.policy().template_only


def test_billing_error_forces_red_and_alert():
    g = gov()
    g.mark_billing_error()
    assert g.state() is b.BudgetState.RED
    assert [a.kind for a in b.pending_alerts(g)] == ["spend_cap_402"]
    assert b.pending_alerts(g) == []  # once per day


def test_alerts_70_and_90():
    g = gov()
    spend(g, 7)
    assert [a.kind for a in b.pending_alerts(g)] == ["budget_70"]
    spend(g, 2.5)
    assert {a.kind for a in b.pending_alerts(g)} == {"budget_90"}


def test_reserve_locked_then_unlocked():
    lim = b.BudgetLimits(daily_usd=10, demo_reserve_usd=4, event_usd=1000, per_task_usd=1000)
    g = b.BudgetGovernor(lim, P, clock=CLOCK)
    spend(g, 5)
    with pytest.raises(b.BudgetExceeded):
        g.check("m", 2000, 0)  # would dip into the reserve
    g.limits = b.BudgetLimits(daily_usd=10, demo_reserve_usd=4, reserve_unlocked=True, event_usd=1000,
                              per_task_usd=1000)
    g.check("m", 2000, 0)


def test_task_and_patient_caps():
    lim = b.BudgetLimits(daily_usd=100, demo_reserve_usd=0, per_task_usd=0.5, per_patient_tokens=1000)
    g = b.BudgetGovernor(lim, P, clock=CLOCK)
    with pytest.raises(b.BudgetExceeded) as e:
        g.check("m", 600, 0, task_id="t1")
    assert e.value.cap == "per_task"
    with pytest.raises(b.BudgetExceeded) as e:
        g.check("m", 400, 700, patient_id="p1")
    assert e.value.cap == "per_patient_tokens"


def test_circuit_breaker():
    g = gov()
    br = b.RunBreaker(2, 1, "r1", on_trip=g.record_safety_stop)
    br.tool_call()
    br.tool_call()
    with pytest.raises(b.CircuitBreakerTripped) as e:
        br.tool_call()
    assert e.value.needs_human_payload()["kind"] == "needs_a_human"
    with br.subagent():
        with pytest.raises(b.CircuitBreakerTripped):
            with br.subagent():
                pass
    assert g.safety_stops == 2 and b.usage_numbers(g).safety_stops == 2


def test_usage_numbers_shape():
    g = gov()
    g.record(model="m", tokens_in=1000, tokens_out=0, task_type="narrate")
    n = b.usage_numbers(g, 12.34)
    assert n.spend_by_task_type == {"narrate": 1.0} and n.today_pct == 10.0 and n.provider_limit_pct == 12.3


# ---------------- retry
class Err(Exception):
    def __init__(self, status, msg="", retry_after=None):
        super().__init__(msg)
        self.status_code = status
        self.response = SimpleNamespace(headers={"Retry-After": str(retry_after)} if retry_after else {})


@pytest.mark.parametrize("exc,cls", [
    (Err(429), "retryable"), (Err(503), "retryable"), (TimeoutError(), "retryable"),
    (Err(402), "spend_cap"), (Err(429, "insufficient_quota"), "spend_cap"),
    (Err(401), "auth"), (Err(403), "auth"), (Err(422), "invalid"), (ValueError("x"), "invalid"),
    (RuntimeError("?"), "unknown")])
def test_classify(exc, cls):
    assert classify(exc).error_class == cls


def flaky(errors, result="ok"):
    calls = []

    def fn():
        calls.append(1)
        if len(calls) <= len(errors):
            raise errors[len(calls) - 1]
        return result
    return fn, calls


def test_429_honours_retry_after():
    fn, calls = flaky([Err(429, retry_after=7)])
    sleeps = []
    assert call_with_retry(fn, sleep=sleeps.append) == "ok"
    assert sleeps == [7.0] and len(calls) == 2


@pytest.mark.parametrize("status", [402, 401, 403, 422])
def test_never_retried(status):
    fn, calls = flaky([Err(status)] * 5)
    with pytest.raises(ProviderCallFailed):
        call_with_retry(fn, sleep=lambda s: None)
    assert len(calls) == 1


def test_503_retries_with_cap():
    fn, calls = flaky([Err(503)] * 10)
    with pytest.raises(ProviderCallFailed) as e:
        call_with_retry(fn, RetryPolicy(max_attempts=3), sleep=lambda s: None, rand=lambda: 0.5)
    assert len(calls) == 3 and e.value.error_class == "retryable"


def test_max_total_wait():
    fn, calls = flaky([Err(429, retry_after=30)] * 5)
    with pytest.raises(ProviderCallFailed):
        call_with_retry(fn, RetryPolicy(max_total_wait=45), sleep=lambda s: None)
    assert len(calls) == 2


def test_fallback_only_when_allowed_and_retryable():
    def fb():
        return "fb"

    pol = RetryPolicy(max_attempts=1)
    f1, _ = flaky([Err(503)])
    assert call_with_fallback(f1, fb, policy=pol, sleep=lambda s: None) == "fb"
    f2, _ = flaky([Err(503)])
    with pytest.raises(ProviderCallFailed):
        call_with_fallback(f2, fb, allow_fallback=lambda: False, policy=pol, sleep=lambda s: None)
    for status in (402, 401):
        f3, _ = flaky([Err(status)])
        with pytest.raises(ProviderCallFailed):
            call_with_fallback(f3, fb, policy=pol, sleep=lambda s: None)


def test_rate_limiter_waits():
    t = [0.0]
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        t[0] += s

    rl = RateLimiter(60, 6000, clock=lambda: t[0], sleep=sleep)
    for _ in range(60):
        rl.acquire(1)
    assert not sleeps and rl.utilisation() > 0.9
    rl.acquire(1)
    assert sleeps and sleeps[0] == pytest.approx(1.0)


# ---------------- PII + llm
def test_pii_guard():
    raw = "call 9876543210 or mail a.b@example.com"
    with pytest.raises(PIILeak):
        assert_clean(raw)
    clean = tokenize(raw)
    assert "9876543210" not in clean and "example.com" not in clean
    assert_clean(clean)
    assert tokenize("Dr. Ravi Kumar") == "[NAME_1]"


ENV = {"WORKER_MODEL": "openai:w", "ORCHESTRATOR_MODEL": "openai:o", "ORCHESTRATOR_FALLBACK_MODEL": "deepseek:d",
       "VISION_MODEL": "openai:v"}


class FakeChat:
    def __init__(self, spec, fail=None):
        self.spec, self.fail, self.n = spec, fail, 0

    def invoke(self, messages, **kw):
        self.n += 1
        if self.fail:
            raise self.fail
        return SimpleNamespace(content="hi", usage_metadata={"input_tokens": 10, "output_tokens": 5})


def lim():
    return RateLimiter(1e6, 1e9)


def test_deepseek_refused_for_real_data():
    with pytest.raises(llm.ModelConfigError):
        llm.get_model("ORCHESTRATOR", env={**ENV, "ORCHESTRATOR_MODEL": "deepseek:d", "CM_DATA_CLASS": "real"})
    with pytest.raises(llm.ModelConfigError):  # fallback path too
        llm.resolve_spec("ORCHESTRATOR", fallback=True, env={**ENV, "CM_DATA_CLASS": "real"})
    with pytest.raises(llm.ModelConfigError):
        llm.get_model("VISION", env={"VISION_MODEL": "deepseek:x", "CM_DATA_CLASS": "real"})
    with pytest.raises(llm.ModelConfigError):
        llm.get_model("EMBEDDING", env={"EMBEDDING_MODEL": "deepseek:x"})
    assert llm.get_model("VISION", env={"VISION_MODEL": "deepseek:x"}).role == "VISION"


def test_get_model_blocks_raw_pii_and_records_usage():
    g = gov()
    made = {}
    m = llm.get_model("WORKER", governor=g, env=ENV, limiter=lim(),
                      builder=lambda s, r: made.setdefault(s, FakeChat(s)))
    with pytest.raises(PIILeak):
        m.invoke("patient phone 9876543210")
    assert made == {}  # nothing left the process
    m.invoke("hello", task_id="t", task_type="narrate")
    assert b.usage_numbers(g).spend_by_task_type["narrate"] > 0


def test_amber_downgrades_red_blocks_and_402_flips_red():
    g = gov()
    made = {}

    def mk():
        return llm.get_model("ORCHESTRATOR", governor=g, env=ENV, limiter=lim(),
                             builder=lambda s, r: made.setdefault(s, FakeChat(s)))

    spend(g, 8)
    mk().invoke("hi")
    assert "openai:w" in made and "openai:o" not in made
    spend(g, 2)
    with pytest.raises(b.TemplateOnlyMode):
        mk().invoke("hi")

    g2 = gov()
    bad = llm.get_model("WORKER", governor=g2, env=ENV, limiter=lim(),
                        builder=lambda s, r: FakeChat(s, fail=Err(402)))
    with pytest.raises(ProviderCallFailed):
        bad.invoke("hi")
    assert g2.state() is b.BudgetState.RED


def test_fallback_blocked_when_unaffordable(monkeypatch):
    monkeypatch.setattr("cm.core.retry.time.sleep", lambda s: None)
    g = gov()
    made = {}

    def builder(s, r):
        return made.setdefault(s, FakeChat(s, fail=Err(503) if s == "openai:o" else None))

    m = llm.get_model("ORCHESTRATOR", governor=g, env=ENV, limiter=lim(), builder=builder)
    m.invoke("hi")
    assert made["deepseek:d"].n == 1  # failed over
    made.clear()
    g.can_afford = lambda *a, **k: False
    with pytest.raises(ProviderCallFailed):
        m.invoke("hi")
    assert "deepseek:d" not in made
