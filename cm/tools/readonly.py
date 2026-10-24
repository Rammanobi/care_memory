"""Read-only, governed tools for the agents (no raw SQL here: reads go through cm.store).

Each tool is wrapped by ``governed``: run breaker (max tool calls), PII tokenize on the way out, and for
patient-facing output a banned-term check that raises instead of returning the text.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from langchain_core.tools import StructuredTool

from cm.agents.context import RunContext
from cm.core.tokenize import tokenize
from cm.memory.features import cite_id
from cm.validator.banned_terms import find_banned_terms


class BannedTermError(ValueError):
    """Patient-facing output contained a banned term."""


def governed(ctx: RunContext, name: str, fn: Callable[..., Any], *, patient_facing: bool = False) -> Callable[..., str]:
    def run(**kw: Any) -> str:
        if ctx.breaker:
            ctx.breaker.tool_call()
        ctx.tool_calls.append(name)
        out = tokenize(json.dumps(fn(**kw), default=str, ensure_ascii=False))
        if patient_facing and (hits := find_banned_terms(out, "en")):
            raise BannedTermError(f"banned term in {name} output: {hits[0]}")
        return out

    run.__name__ = name
    return run


def event_row(e: dict[str, Any]) -> dict[str, Any]:
    p = e.get("payload") or {}
    keep = {k: p[k] for k in ("status", "reason", "kind", "text", "why", "title") if k in p}
    return {"id": cite_id(e), "type": e["type"], "date": e["occurred_at"].date().isoformat(),
            "source": e.get("source"), **keep}


def build_tools(ctx: RunContext) -> list[StructuredTool]:
    def get_patient_snapshot() -> dict[str, Any]:
        return {"patient": ctx.token, "as_of": ctx.features.as_of.isoformat(), "events_known": len(ctx.events),
                "checkins_total": ctx.features.checkins_total, "missed_7d": ctx.features.missed_7d}

    def list_events(types: list[str] | None = None, limit: int = 20) -> list[dict[str, Any]]:
        rows = [e for e in ctx.events if not types or e["type"] in types]
        return [event_row(e) for e in rows[: max(1, min(limit, 40))]]

    def compute_features() -> dict[str, Any]:
        return ctx.features.as_dict()

    specs = [
        (get_patient_snapshot, "Counts and as_of date for the patient under review."),
        (list_events, "Recent events with citation ids (newest first). Optional types filter, limit up to 40."),
        (compute_features, "Computed numbers (missed doses, streak, refill gap, quiet days, conflicts) with the "
                           "citation ids that back each one. The only source of numbers."),
    ]
    return [StructuredTool.from_function(governed(ctx, f.__name__, f), name=f.__name__, description=d,
                                         args_schema=_schema(f)) for f, d in specs]


def _schema(fn: Callable[..., Any]) -> Any:
    from pydantic import create_model

    if fn.__name__ == "list_events":
        return create_model("ListEventsArgs", types=(list[str] | None, None), limit=(int, 20))
    return create_model(fn.__name__ + "_args")
