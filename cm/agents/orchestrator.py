"""Orchestrator deep agent: plan with write_todos, read with the read-only tools, write one cited card,
then pause at submit_for_review (human-in-the-loop interrupt) before a pending approval is created.

Nothing here writes the outbox. The approval row is the doctor's queue item; only cm.review.decide can
turn a decision into an outbox row.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.tools import StructuredTool
from langgraph.types import Command
from pydantic import create_model

from cm.agents.context import RunContext
from cm.agents.narrator import Card, evidence_for, write_card
from cm.memory.features import PatientFeatures, suggest_tier
from cm.tools.readonly import BannedTermError, build_tools, governed
from cm.validator.banned_terms import find_banned_terms
from cm.validator.cite_or_cut import cite_or_cut, refs_of

SYSTEM_PROMPT = """You prepare one memory card for the treating doctor about ONE patient.
Work in this order and do not skip steps:
1. Call write_todos with a short plan.
2. Call get_patient_snapshot, then compute_features, then list_events (limit 15).
3. Call write_card once. It writes and checks the card itself; do not rewrite its sentences.
4. Call submit_for_review with the card_id from write_card.
5. Reply with one line: the tier and how many sentences the card has.
Never state a number yourself; numbers come only from tools. No advice, no diagnosis."""

ApprovalWriter = Callable[..., UUID]


def _evidence_items(ctx: RunContext, card: Card) -> list[dict[str, Any]]:
    from cm.memory.features import cite_id

    by_cite = {cite_id(e): e for e in ctx.events}
    items: list[dict[str, Any]] = []
    for r in dict.fromkeys(r for s in card.sentences for r in refs_of(s)):
        e = by_cite.get(r)
        if not e or len(items) >= 6:
            continue
        p = e.get("payload") or {}
        items.append({
            "kind": "event", "label": f"{e['type']} {p.get('status') or p.get('text') or ''}".strip(),
            "value": e["occurred_at"].date().isoformat(), "source": e.get("source"),
            "citation": {"label": r, "ref_id": str(e["event_id"]), "sim_day": 0, "ref_type": "E"},
        })
    return items


def build_orchestrator(model: Any, ctx: RunContext, *, checkpointer: Any = None, subagent_model: Any = None,
                       write_approval: ApprovalWriter | None = None) -> Any:
    """Compile the deep agent. ``model`` and ``subagent_model`` are chat models (governed or fake)."""
    if write_approval is None:
        from cm.store.ai_repo import create_card_approval as write_approval

    def do_write_card() -> dict[str, Any]:
        card = write_card(ctx.features, ctx.model, task_id=ctx.task_id, patient_id=str(ctx.patient_id))
        cid = f"card-{len(ctx.cards) + 1}"
        ctx.cards[cid] = {"card": card}
        return {"card_id": cid, "source": card.source, "reason": card.reason, "sentences": card.sentences,
                "cut": len(card.cut)}

    def do_submit(card_id: str) -> dict[str, Any]:
        item = ctx.cards.get(card_id)
        if not item:
            raise ValueError(f"unknown card_id {card_id}")
        card: Card = item["card"]
        if cite_or_cut(card.sentences, evidence_for(ctx.features)).cut:  # defence in depth
            raise ValueError("card failed cite-or-cut at submit")
        if hits := find_banned_terms(card.text, "en"):
            raise BannedTermError(f"banned term in draft: {hits[0]}")
        tier = suggest_tier(ctx.features)
        created = ctx.as_of
        payload = {
            "audience": "doctor", "title": f"Memory card - {ctx.token}", "body": card.text,
            "sentences": [{"text": s, "refs": refs_of(s)} for s in card.sentences],
            "subkind": "nightly_card", "data": {"numbers": ctx.features.numbers, "source": card.source,
                                                 "reason": card.reason, "task_id": ctx.task_id},
        }
        aid = write_approval(patient_id=ctx.patient_id, thread_id=ctx.thread_id, interrupt_id=card_id, tier=tier,
                             payload=payload, evidence=_evidence_items(ctx, card), created_at=created)
        ctx.approvals.append(str(aid))
        return {"approval_id": str(aid), "tier": tier, "status": "pending"}

    card_args = create_model("SubmitArgs", card_id=(str, ...))
    extra = [
        StructuredTool.from_function(governed(ctx, "write_card", do_write_card), name="write_card",
                                     description="Write the cited doctor card from computed features.",
                                     args_schema=create_model("WriteCardArgs")),
        StructuredTool.from_function(governed(ctx, "submit_for_review", do_submit), name="submit_for_review",
                                     description="Put the card into the doctor's review queue as a pending draft.",
                                     args_schema=card_args),
    ]
    tools = [*build_tools(ctx), *extra]
    read_names = {t.name for t in tools[:3]}
    sub_model = subagent_model or model
    subagents = [
        {"name": "narrator", "description": "Writes the cited doctor card (use write_card).",
         "system_prompt": "Write the card with write_card only.", "tools": [t for t in tools if t.name == "write_card"],
         "model": sub_model},
        {"name": "drafter", "description": "Drafts short patient-safe wording; reads features only.",
         "system_prompt": "Use compute_features for numbers; plain words; no disease or drug names.",
         "tools": [t for t in tools if t.name in read_names], "model": sub_model},
    ]
    return create_deep_agent(model=model, tools=tools, system_prompt=SYSTEM_PROMPT, subagents=subagents,
                             interrupt_on={"submit_for_review": True}, checkpointer=checkpointer,
                             middleware=[TodoListMiddleware()])


def run(agent: Any, ctx: RunContext, *, resume: str | None = None) -> dict[str, Any]:
    """Start (resume=None) or resume ('approve'|'reject') the thread. Returns a small status dict."""
    cfg = {"configurable": {"thread_id": ctx.thread_id}, "recursion_limit": 60}
    if resume is None:
        msg = {"messages": [{"role": "user", "content": f"Prepare tonight's card for {ctx.token}."}]}
        out = agent.invoke(msg, cfg, durability="sync")
    else:
        out = agent.invoke(Command(resume={"decisions": [{"type": resume}]}), cfg, durability="sync")
    todos = out.get("todos") or (agent.get_state(cfg).values or {}).get("todos") or []
    status = "interrupted" if out.get("__interrupt__") else "done"
    return {"status": status, "todos": todos, "approvals": list(ctx.approvals), "tool_calls": list(ctx.tool_calls),
            "final": _last_text(out)}


def _last_text(out: dict[str, Any]) -> str:
    msgs = out.get("messages") or []
    c = getattr(msgs[-1], "content", "") if msgs else ""
    return c if isinstance(c, str) else json.dumps(c)


__all__ = ["build_orchestrator", "run", "PatientFeatures"]
