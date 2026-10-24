"""AI budget governor (AI_LIMITS_AND_CAPS.md): four caps, GREEN/AMBER/RED, circuit breaker, alerts, admin numbers.

Pure Python. Running totals sit behind the ``UsageStore`` Protocol; the real store (task_runs
tokens_in/tokens_out/cost_usd) is wired later. No model names or keys live here.
"""

from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel

AMBER_AT = 0.70
RED_ABOVE = 0.90


class BudgetState(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


# ---------------------------------------------------------------- typed errors
class BudgetError(Exception):
    """Base class. ``error_class`` matches task_runs.error_class."""

    error_class = "spend_cap"


class BudgetExceeded(BudgetError):
    def __init__(self, cap: str, detail: str = "") -> None:
        super().__init__(f"budget cap hit: {cap} {detail}".strip())
        self.cap = cap


class TemplateOnlyMode(BudgetError):
    """RED state: no LLM drafting; callers use rules and approved templates."""


class CircuitBreakerTripped(Exception):
    """Runtime turns this into a 'needs a human' review item (see ``needs_human_payload``)."""

    def __init__(self, reason: str, run_id: str = "", limit: int = 0) -> None:
        super().__init__(f"circuit breaker: {reason}")
        self.reason, self.run_id, self.limit = reason, run_id, limit

    def needs_human_payload(self) -> dict[str, Any]:
        return {
            "kind": "needs_a_human",
            "run_id": self.run_id,
            "reason": self.reason,
            "limit": self.limit,
            "summary": "An automated run was stopped by a safety limit. Please review it.",
        }


# ---------------------------------------------------------------- config
@dataclass(frozen=True)
class BudgetLimits:
    daily_usd: float = 5.0  # global daily cap, reserve included
    per_task_usd: float = 0.25
    per_patient_tokens: int = 60_000  # per patient per day
    demo_reserve_usd: float = 1.25  # locked until reserve_unlocked
    reserve_unlocked: bool = False
    event_usd: float = 25.0  # whole-event budget (display + hard stop)
    max_tool_calls: int = 40
    max_subagent_depth: int = 2
    amber_draft_tokens: int = 300
    green_draft_tokens: int = 800

    @property
    def spendable_usd(self) -> float:
        return self.daily_usd if self.reserve_unlocked else max(self.daily_usd - self.demo_reserve_usd, 0.0)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> BudgetLimits:
        e = os.environ if env is None else env
        d = cls()

        def f(name: str, default: float) -> float:
            return float(e.get(name, default))

        return cls(
            daily_usd=f("CM_BUDGET_DAILY_USD", d.daily_usd),
            per_task_usd=f("CM_BUDGET_TASK_USD", d.per_task_usd),
            per_patient_tokens=int(f("CM_BUDGET_PATIENT_TOKENS", d.per_patient_tokens)),
            demo_reserve_usd=f("CM_BUDGET_RESERVE_USD", d.demo_reserve_usd),
            reserve_unlocked=e.get("CM_BUDGET_RESERVE_UNLOCKED", "0").lower() in {"1", "true", "yes"},
            event_usd=f("CM_BUDGET_EVENT_USD", d.event_usd),
            max_tool_calls=int(f("CM_MAX_TOOL_CALLS", d.max_tool_calls)),
            max_subagent_depth=int(f("CM_MAX_SUBAGENT_DEPTH", d.max_subagent_depth)),
        )


@dataclass(frozen=True)
class PriceTable:
    """USD per 1k tokens, keyed by the model name read from env. Unknown models use ``default``."""

    prices: dict[str, tuple[float, float]] = field(default_factory=dict)  # name -> (in, out)
    default: tuple[float, float] = (0.01, 0.03)  # deliberately pessimistic

    def cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        pin, pout = self.prices.get(model, self.default)
        return tokens_in / 1000 * pin + tokens_out / 1000 * pout

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> PriceTable:
        """CM_PRICE_TABLE_JSON like {"<model>": [in_per_1k, out_per_1k]}."""
        e = os.environ if env is None else env
        raw = json.loads(e.get("CM_PRICE_TABLE_JSON", "{}") or "{}")
        return cls({k: (float(v[0]), float(v[1])) for k, v in raw.items()})


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


# ---------------------------------------------------------------- storage
class UsageStore(Protocol):
    def add(self, *, day: str, task_id: str, task_type: str, patient_id: str | None,
            tokens_in: int, tokens_out: int, cost_usd: float) -> None: ...
    def day_cost(self, day: str) -> float: ...
    def total_cost(self) -> float: ...
    def task_cost(self, task_id: str) -> float: ...
    def patient_tokens(self, day: str, patient_id: str) -> int: ...
    def cost_by_task_type(self, day: str) -> dict[str, float]: ...


class InMemoryUsageStore:
    def __init__(self) -> None:
        self._day: dict[str, float] = defaultdict(float)
        self._task: dict[str, float] = defaultdict(float)
        self._pat: dict[tuple[str, str], int] = defaultdict(int)
        self._types: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    def add(self, *, day: str, task_id: str, task_type: str, patient_id: str | None,
            tokens_in: int, tokens_out: int, cost_usd: float) -> None:
        self._day[day] += cost_usd
        self._task[task_id] += cost_usd
        self._types[day][task_type] += cost_usd
        if patient_id:
            self._pat[(day, patient_id)] += tokens_in + tokens_out

    def day_cost(self, day: str) -> float:
        return self._day[day]

    def total_cost(self) -> float:
        return sum(self._day.values())

    def task_cost(self, task_id: str) -> float:
        return self._task[task_id]

    def patient_tokens(self, day: str, patient_id: str) -> int:
        return self._pat[(day, patient_id)]

    def cost_by_task_type(self, day: str) -> dict[str, float]:
        return dict(self._types[day])


# ---------------------------------------------------------------- policy
@dataclass(frozen=True)
class Policy:
    state: BudgetState
    model_tier: str  # "primary" | "worker" | "none"
    allow_optional_subagents: bool
    max_draft_tokens: int
    template_only: bool


def _default_now() -> datetime:
    try:
        from cm.core.clock import now  # backend-owned

        return now()
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc)  # only if the clock lane is absent


@dataclass
class OwnerAlert:
    """Data only; sending is another lane (outbox system kinds)."""

    kind: str  # budget_70 | budget_90 | spend_cap_402
    severity: str  # info | warn | critical
    title: str
    body: str
    day: str
    pct: float
    dedupe_key: str


class BudgetGovernor:
    def __init__(self, limits: BudgetLimits | None = None, prices: PriceTable | None = None,
                 store: UsageStore | None = None, clock: Callable[[], datetime] = _default_now) -> None:
        self.limits = limits or BudgetLimits()
        self.prices = prices or PriceTable()
        self.store: UsageStore = store or InMemoryUsageStore()
        self._clock = clock
        self.billing_error = False
        self.safety_stops = 0
        self._alerted: set[str] = set()

    def today(self) -> str:
        return self._clock().date().isoformat()

    # state
    def pct_used(self) -> float:
        cap = self.limits.spendable_usd
        spent = self.store.day_cost(self.today())
        return spent / cap if cap > 0 else 1.0

    def state(self) -> BudgetState:
        p = self.pct_used()
        if self.billing_error or p > RED_ABOVE:
            return BudgetState.RED
        return BudgetState.AMBER if p >= AMBER_AT else BudgetState.GREEN

    def policy(self) -> Policy:
        s = self.state()
        if s is BudgetState.RED:
            return Policy(s, "none", False, 0, True)
        if s is BudgetState.AMBER:
            return Policy(s, "worker", False, self.limits.amber_draft_tokens, False)
        return Policy(s, "primary", True, self.limits.green_draft_tokens, False)

    def mark_billing_error(self) -> None:
        """402 / spend-cap from a provider: RED until cleared by the owner."""
        self.billing_error = True

    def clear_billing_error(self) -> None:
        self.billing_error = False

    def record_safety_stop(self) -> None:
        self.safety_stops += 1

    # pre-call / post-call
    def estimate_cost(self, model: str, est_in: int, est_out: int) -> float:
        return self.prices.cost(model, est_in, est_out)

    def can_afford(self, model: str, est_in: int, est_out: int, *, task_id: str = "",
                   patient_id: str | None = None) -> bool:
        try:
            self.check(model, est_in, est_out, task_id=task_id, patient_id=patient_id)
            return True
        except BudgetExceeded:
            return False

    def check(self, model: str, est_in: int, est_out: int, *, task_id: str = "",
              patient_id: str | None = None) -> float:
        """Raise BudgetExceeded if the call could break a cap; return the estimated cost."""
        if self.billing_error:
            raise BudgetExceeded("billing_error")
        est = self.estimate_cost(model, est_in, est_out)
        day = self.today()
        if self.store.day_cost(day) + est > self.limits.spendable_usd:
            raise BudgetExceeded("daily" if self.limits.reserve_unlocked else "daily_or_reserve")
        if self.store.total_cost() + est > self.limits.event_usd:
            raise BudgetExceeded("event")
        if task_id and self.store.task_cost(task_id) + est > self.limits.per_task_usd:
            raise BudgetExceeded("per_task", task_id)
        if patient_id and (self.store.patient_tokens(day, patient_id) + est_in + est_out
                           > self.limits.per_patient_tokens):
            raise BudgetExceeded("per_patient_tokens")
        return est

    def record(self, *, model: str, tokens_in: int, tokens_out: int, task_id: str = "adhoc",
               task_type: str = "other", patient_id: str | None = None) -> float:
        cost = self.prices.cost(model, tokens_in, tokens_out)
        self.store.add(day=self.today(), task_id=task_id, task_type=task_type, patient_id=patient_id,
                       tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost)
        return cost

    def new_breaker(self, run_id: str = "") -> RunBreaker:
        return RunBreaker(self.limits.max_tool_calls, self.limits.max_subagent_depth, run_id,
                          on_trip=self.record_safety_stop)


# ---------------------------------------------------------------- circuit breaker
class RunBreaker:
    """One per agent run. ``tool_call()`` before each tool; ``subagent()`` around each sub-agent."""

    def __init__(self, max_tool_calls: int, max_depth: int, run_id: str = "",
                 on_trip: Callable[[], None] | None = None) -> None:
        self.max_tool_calls, self.max_depth, self.run_id = max_tool_calls, max_depth, run_id
        self.tool_calls = 0
        self.depth = 0
        self._on_trip = on_trip

    def _trip(self, reason: str, limit: int) -> None:
        if self._on_trip:
            self._on_trip()
        raise CircuitBreakerTripped(reason, self.run_id, limit)

    def tool_call(self) -> None:
        self.tool_calls += 1
        if self.tool_calls > self.max_tool_calls:
            self._trip("max_tool_calls", self.max_tool_calls)

    @contextmanager
    def subagent(self) -> Iterator[None]:
        if self.depth + 1 > self.max_depth:
            self._trip("max_subagent_depth", self.max_depth)
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1


# ---------------------------------------------------------------- alerts
def pending_alerts(gov: BudgetGovernor) -> list[OwnerAlert]:
    """New owner alerts at 70%, 90% and on a billing error; each fires once per day."""
    day, pct, out = gov.today(), gov.pct_used(), []

    def add(kind: str, sev: str, title: str, body: str) -> None:
        key = f"{kind}:{day}"
        if key not in gov._alerted:
            gov._alerted.add(key)
            out.append(OwnerAlert(kind, sev, title, body, day, round(pct * 100, 1), key))

    if gov.billing_error:
        add("spend_cap_402", "critical", "AI provider credits exhausted",
            "A provider returned 402 or a spend-cap error. Template-only mode is on. Top up credits.")
    if pct > RED_ABOVE:
        add("budget_90", "critical", "AI budget over 90% today", "Template-only mode is active.")
    if pct >= AMBER_AT:
        add("budget_70", "warn", "AI budget at 70% today", "Cheaper model and shorter drafts are in use.")
    return out


# ---------------------------------------------------------------- admin numbers
class UsageCapsPanel(BaseModel):
    state: str
    today_spent_usd: float
    today_cap_usd: float
    today_pct: float
    reserve_locked_usd: float
    event_spent_usd: float
    event_budget_usd: float
    provider_limit_pct: float
    spend_by_task_type: dict[str, float]
    safety_stops: int
    billing_error: bool


def usage_numbers(gov: BudgetGovernor, provider_limit_pct: float = 0.0) -> UsageCapsPanel:
    """Shape for the Admin usage-and-caps panel. ``provider_limit_pct`` = RateLimiter.utilisation()*100."""
    day = gov.today()
    return UsageCapsPanel(
        state=gov.state().value,
        today_spent_usd=round(gov.store.day_cost(day), 6),
        today_cap_usd=gov.limits.spendable_usd,
        today_pct=round(gov.pct_used() * 100, 1),
        reserve_locked_usd=0.0 if gov.limits.reserve_unlocked else gov.limits.demo_reserve_usd,
        event_spent_usd=round(gov.store.total_cost(), 6),
        event_budget_usd=gov.limits.event_usd,
        provider_limit_pct=round(provider_limit_pct, 1),
        spend_by_task_type={k: round(v, 6) for k, v in gov.store.cost_by_task_type(day).items()},
        safety_stops=gov.safety_stops,
        billing_error=gov.billing_error,
    )
