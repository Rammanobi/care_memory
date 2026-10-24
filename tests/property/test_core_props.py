"""Property tests for pure cm/core logic: clock (IST labels), PII tokenizer, budget governor, retry."""

from __future__ import annotations

import contextlib
import math
import re
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from cm.core import clock
from cm.core.budget import (
    AMBER_AT,
    RED_ABOVE,
    BudgetExceeded,
    BudgetGovernor,
    BudgetLimits,
    BudgetState,
    PriceTable,
    RunBreaker,
    pending_alerts,
)
from cm.core.retry import (
    ProviderCallFailed,
    RateLimiter,
    RetryPolicy,
    TokenBucket,
    call_with_retry,
    classify,
)
from cm.core.tokenize import assert_clean, clear_names, tokenize

FAST = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])

aware = st.datetimes(
    min_value=datetime(2020, 1, 1), max_value=datetime(2035, 1, 1), timezones=st.just(UTC)
)
offsets = st.integers(min_value=-12 * 60, max_value=14 * 60).map(
    lambda m: timezone(timedelta(minutes=m))
)


# ----------------------------------------------------------------------------- clock
@FAST
@given(aware, offsets)
def test_ist_date_is_tz_independent(at: datetime, tz: timezone) -> None:
    expected = (at.astimezone(UTC) + timedelta(hours=5, minutes=30)).date()
    assert clock.ist_date(at) == expected
    assert clock.ist_date(at.astimezone(tz)) == expected


@FAST
@given(st.dates(min_value=date(2020, 1, 1), max_value=date(2035, 1, 1)), st.integers(0, 400))
def test_sim_instant_labels_and_spacing(day0: date, n: int) -> None:
    a, b = clock.sim_instant(day0, n), clock.sim_instant(day0, n + 1)
    assert a.tzinfo is not None
    assert clock.ist_date(a) == day0 + timedelta(days=n)
    assert b - a == timedelta(days=1)
    assert a.astimezone(clock.IST).hour == 18


def test_clinic_pin_overrides_global() -> None:
    g, c = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)
    try:
        clock.pin(g)
        clock.pin(c, clinic_id="X")
        assert clock.now("X") == c and clock.now("Y") == g and clock.now() == g
    finally:
        clock.unpin("X")
        clock.unpin()


# ----------------------------------------------------------------------------- tokenizer
def _mobile() -> st.SearchStrategy[str]:
    digits = st.tuples(st.sampled_from("6789"), st.text("0123456789", min_size=9, max_size=9)).map(
        "".join
    )
    prefix = st.sampled_from(["", "+91", "+91 ", "+91-", "91", "91 ", "0"])

    def fmt(p: str, d: str, style: int) -> str:
        body = [d, f"{d[:5]} {d[5:]}", f"{d[:5]}-{d[5:]}", f"{d[:3]} {d[3:6]} {d[6:]}",
                f"{d[:4]} {d[4:7]} {d[7:]}", f"{d[:3]}-{d[3:6]}-{d[6:]}"][style]  # fmt: skip
        return p + body

    return st.builds(fmt, prefix, digits, st.integers(0, 5))


def _aadhaar() -> st.SearchStrategy[str]:
    d = st.tuples(st.sampled_from("23456789"), st.text("0123456789", min_size=11, max_size=11))
    sep = st.sampled_from([" ", "-", ""])
    return st.builds(lambda t, s: f"{t[0]}{t[1][:3]}{s}{t[1][3:7]}{s}{t[1][7:]}", d, sep)


filler = st.text(alphabet="abcdefghij klmnop,.:;", max_size=20)


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


@FAST
@given(filler, _mobile(), filler)
def test_phone_never_survives_tokenize(pre: str, phone: str, post: str) -> None:
    out = tokenize(f"{pre} call {phone} {post}")
    core = _digits(phone)[-10:]
    assert core not in _digits(out), out
    assert_clean(out)


@FAST
@given(filler, _aadhaar(), filler)
def test_aadhaar_never_survives_tokenize(pre: str, aad: str, post: str) -> None:
    out = tokenize(f"{pre} aadhaar {aad} {post}")
    assert _digits(aad) not in _digits(out), out
    for block in re.findall(r"\d{4}", aad):
        assert block not in out, out
    assert_clean(out)


@FAST
@given(filler, _mobile(), _aadhaar())
def test_tokenize_is_idempotent_and_stable(pre: str, phone: str, aad: str) -> None:
    text = f"{pre} {phone} and {aad} and {phone} again"
    once = tokenize(text)
    assert tokenize(once) == once
    assert tokenize(text) == once  # deterministic
    assert once.count("[PHONE_1]") == 2  # same value, same token


@FAST
@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ,.", max_size=80))
def test_tokenize_leaves_plain_text_alone(text: str) -> None:
    clear_names()
    assert tokenize(text) == text


@FAST
@given(st.from_regex(r"[A-Z][a-z]{3,8}", fullmatch=True), filler)
def test_known_names_scrubbed_case_insensitively(name: str, pre: str) -> None:
    out = tokenize(f"{pre} {name.upper()} said hi", names=[name])
    assert name.lower() not in out.lower()
    assert_clean(out, names=[name])


# ----------------------------------------------------------------------------- budget governor
class _Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


def _gov(at: datetime | None = None, **kw: float) -> tuple[BudgetGovernor, _Clock]:
    c = _Clock(at or datetime(2026, 3, 1, 6, tzinfo=UTC))
    lim = BudgetLimits(**kw) if kw else BudgetLimits()
    return BudgetGovernor(lim, PriceTable({"m": (0.01, 0.03)}), clock=c), c


calls = st.lists(
    st.tuples(st.integers(0, 20_000), st.integers(0, 5_000), st.sampled_from(["t1", "t2", "t3"]),
              st.sampled_from([None, "p1", "p2"])),  # fmt: skip
    max_size=60,
)


@FAST
@given(calls)
def test_governed_spend_never_breaks_a_cap(seq: list) -> None:
    gov, _ = _gov()
    prev = BudgetState.GREEN
    order = {BudgetState.GREEN: 0, BudgetState.AMBER: 1, BudgetState.RED: 2}
    for tin, tout, task, pid in seq:
        if gov.can_afford("m", tin, tout, task_id=task, patient_id=pid):
            assert gov.record(model="m", tokens_in=tin, tokens_out=tout, task_id=task,
                              patient_id=pid) >= 0  # fmt: skip
        day = gov.today()
        assert 0 <= gov.store.day_cost(day) <= gov.limits.spendable_usd + 1e-9
        assert gov.store.total_cost() <= gov.limits.event_usd + 1e-9
        assert gov.store.task_cost(task) <= gov.limits.per_task_usd + 1e-9
        if pid:
            assert gov.store.patient_tokens(day, pid) <= gov.limits.per_patient_tokens
        s = gov.state()
        assert order[s] >= order[prev], "state went backwards within a day"
        prev = s
        assert gov.pct_used() >= 0


@FAST
@given(st.floats(min_value=0, max_value=10, allow_nan=False))
def test_state_matches_thresholds(spend: float) -> None:
    gov, _ = _gov()
    gov.store.add(day=gov.today(), task_id="x", task_type="other", patient_id=None, tokens_in=0,
                  tokens_out=0, cost_usd=spend)  # fmt: skip
    pct = spend / gov.limits.spendable_usd
    want = (
        BudgetState.RED if pct > RED_ABOVE else BudgetState.AMBER if pct >= AMBER_AT
        else BudgetState.GREEN
    )  # fmt: skip
    assert gov.state() is want
    pol = gov.policy()
    assert pol.template_only == (want is BudgetState.RED)
    assert pol.max_draft_tokens >= 0 and (want is not BudgetState.RED or pol.max_draft_tokens == 0)


def test_billing_error_forces_red_until_cleared() -> None:
    gov, _ = _gov()
    gov.mark_billing_error()
    assert gov.state() is BudgetState.RED
    with pytest.raises(BudgetExceeded):
        gov.check("m", 1, 1)
    gov.clear_billing_error()
    assert gov.state() is BudgetState.GREEN


@FAST
@given(st.integers(0, 23), st.integers(0, 59))
def test_budget_day_is_the_ist_date(hour: int, minute: int) -> None:
    at = datetime(2026, 3, 1, hour, minute, tzinfo=UTC)
    gov, _ = _gov(at)
    assert gov.today() == clock.ist_date(at).isoformat()


def test_new_ist_day_resets_state_and_alerts_fire_once() -> None:
    gov, c = _gov(datetime(2026, 3, 1, 10, tzinfo=UTC))
    gov.store.add(day=gov.today(), task_id="x", task_type="other", patient_id=None, tokens_in=0,
                  tokens_out=0, cost_usd=gov.limits.spendable_usd)  # fmt: skip
    assert gov.state() is BudgetState.RED
    kinds = {a.kind for a in pending_alerts(gov)}
    assert kinds == {"budget_70", "budget_90"}
    assert pending_alerts(gov) == []  # once per day
    c.at = datetime(2026, 3, 1, 19, tzinfo=UTC)  # 00:30 IST next day
    assert gov.state() is BudgetState.GREEN


@FAST
@given(st.integers(1, 50), st.integers(0, 80))
def test_breaker_trips_exactly_after_limit(limit: int, n: int) -> None:
    b = RunBreaker(limit, 2)
    tripped = False
    for _ in range(n):
        try:
            b.tool_call()
        except Exception:  # noqa: BLE001
            tripped = True
            break
    assert tripped == (n > limit)


# ----------------------------------------------------------------------------- retry
class _HttpErr(Exception):
    def __init__(self, status: int, headers: dict | None = None, msg: str = "") -> None:
        super().__init__(msg)
        self.status_code, self.headers = status, headers or {}


statuses = st.sampled_from([400, 401, 402, 403, 404, 413, 422, 429, 500, 502, 503, 504])


@FAST
@given(statuses, st.integers(0, 6), st.integers(1, 6))
def test_retry_only_retryable_and_bounded(status: int, fails: int, max_attempts: int) -> None:
    state = {"n": 0}
    sleeps: list[float] = []

    def fn() -> str:
        state["n"] += 1
        if state["n"] <= fails:
            raise _HttpErr(status)
        return "ok"

    pol = RetryPolicy(max_attempts=max_attempts, base_delay=0.5, max_delay=4, max_total_wait=10)
    retryable = status == 429 or status >= 500
    try:
        assert call_with_retry(fn, pol, sleep=sleeps.append, rand=lambda: 0.5) == "ok"
        assert fails == 0 or (retryable and fails < max_attempts)
    except ProviderCallFailed as e:
        assert fails > 0
        if not retryable:
            assert state["n"] == 1, "non-retryable errors must not be retried"
        assert e.error_class == classify(_HttpErr(status)).error_class
    assert state["n"] <= max_attempts
    assert all(0 <= s <= pol.max_delay for s in sleeps)
    assert sum(sleeps) <= pol.max_total_wait


@FAST
@given(st.one_of(st.floats(allow_nan=True, allow_infinity=True).map(str),
                 st.text(max_size=12), st.integers(-100, 100).map(str)))  # fmt: skip
def test_any_retry_after_header_sleeps_a_finite_nonnegative_time(raw: str) -> None:
    sleeps: list[float] = []
    state = {"n": 0}

    def fn() -> str:
        state["n"] += 1
        if state["n"] == 1:
            raise _HttpErr(503, {"Retry-After": raw})
        return "ok"

    pol = RetryPolicy(max_attempts=3, max_total_wait=30)
    with contextlib.suppress(ProviderCallFailed):
        call_with_retry(fn, pol, sleep=sleeps.append, rand=lambda: 0.5)
    assert all(math.isfinite(s) and s >= 0 for s in sleeps), sleeps
    assert sum(sleeps) <= pol.max_total_wait


@FAST
@given(st.floats(min_value=0, max_value=60, allow_nan=False))
def test_retry_after_is_honoured(ra: float) -> None:
    sleeps: list[float] = []
    state = {"n": 0}

    def fn() -> str:
        state["n"] += 1
        if state["n"] == 1:
            raise _HttpErr(429, {"retry-after": str(ra)})
        return "ok"

    pol = RetryPolicy(max_attempts=3, max_total_wait=45)
    try:
        call_with_retry(fn, pol, sleep=sleeps.append)
        assert sleeps == [ra]
    except ProviderCallFailed:
        assert ra > pol.max_total_wait and sleeps == []


@FAST
@given(st.sampled_from(["insufficient_quota", "Spend cap reached", "billing hard limit"]),
       st.sampled_from([429, 500, 402]))  # fmt: skip
def test_spend_cap_is_never_retried(msg: str, status: int) -> None:
    n = {"c": 0}

    def fn() -> None:
        n["c"] += 1
        raise _HttpErr(status, msg=msg)

    with pytest.raises(ProviderCallFailed) as ei:
        call_with_retry(fn, RetryPolicy(max_attempts=5), sleep=lambda _: None)
    assert ei.value.error_class == "spend_cap" and n["c"] == 1


@FAST
@given(st.integers(1, 120), st.lists(st.integers(1, 400), max_size=30))
def test_rate_limiter_never_overdraws(rpm: int, toks: list[int]) -> None:
    t = {"now": 0.0}
    lim = RateLimiter(rpm, 1000, clock=lambda: t["now"],
                      sleep=lambda s: t.__setitem__("now", t["now"] + s))  # fmt: skip
    for n in toks:
        w = lim.acquire(n)
        assert w >= 0
        assert lim.rpm.level >= -1e-6 and lim.tpm.level >= -1e-6
        assert lim.rpm.level <= lim.rpm.capacity + 1e-9


@FAST
@given(st.floats(min_value=0.1, max_value=1000), st.floats(min_value=0, max_value=5000))
def test_token_bucket_wait_nonnegative(per_min: float, n: float) -> None:
    b = TokenBucket(per_min, clock=lambda: 0.0)
    assume(n >= 0)
    assert b.wait_time(n) >= 0
    assert 0 <= b.utilisation() <= 1
