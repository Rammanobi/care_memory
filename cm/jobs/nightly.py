"""Nightly memory card for one patient: `python -m cm.jobs.nightly --patient PT-0142 [--live] [--force]`.

Without --live a scripted fake model is used (no network, no key). With --live the ORCHESTRATOR model is
called through the budget governor. The interrupt at submit_for_review is answered 'approve' by this system
job, which only releases a PENDING draft into the doctor queue; sending still needs cm.review.decide.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from contextlib import contextmanager
from typing import Any

from cm.agents import fakes
from cm.agents.context import RunContext
from cm.agents.governed_chat import GovernedChat
from cm.agents.orchestrator import build_orchestrator, run
from cm.core import clock, llm
from cm.core.budget_pg import install_governor
from cm.core.config import load_dotenv, load_settings
from cm.core.db import transaction
from cm.core.logging import get_logger
from cm.memory.features import compute_features
from cm.memory.pipeline import run_patient as run_memory
from cm.store import ai_repo, events_repo

log = get_logger(__name__)


@contextmanager
def checkpointer() -> Any:
    """PostgresSaver when the database accepts it, otherwise MemorySaver. Yields (saver, kind)."""
    saver_cm = None
    try:
        from langgraph.checkpoint.postgres import PostgresSaver

        saver_cm = PostgresSaver.from_conn_string(load_settings().dsn)
        saver = saver_cm.__enter__()
        saver.setup()
    except Exception as e:  # DB unreachable or package missing: fall back and say so
        print(f"checkpointer: postgres unavailable ({type(e).__name__}); using MemorySaver")
        from langgraph.checkpoint.memory import MemorySaver

        yield MemorySaver(), "memory"
        return
    try:
        yield saver, "postgres"
    finally:
        saver_cm.__exit__(None, None, None)


def _memory_summary(mem: Any) -> dict[str, Any] | None:
    if mem is None:
        return None
    return {"as_of": mem.as_of.isoformat(), "beliefs": len(mem.beliefs),
            "risk_p": round(mem.risk.p, 4) if mem.risk else None,
            "conflicts": len(mem.conflicts), "engine_conflicts": [c.cref for c in mem.engine_conflicts]}


def run_patient(code: str, *, live: bool = False, force: bool = False) -> dict[str, Any]:
    load_dotenv()
    with transaction() as conn:
        clock.load_pin(conn)
        pid, token = ai_repo.resolve_patient(code, conn=conn)
        day0, sim_day = ai_repo.sim_day0(conn=conn)
    gov = install_governor()
    as_of = clock.now()
    mem = run_memory(pid, as_of, day0=day0)  # persist features, beliefs, risk, conflicts first
    try:  # keep the patient's retrieval index current (idempotent); real embeddings only on live runs
        from cm.jobs.rag_index import index_patient

        index_patient(code, as_of, embed=live)
    except Exception as e:  # noqa: BLE001  retrieval index is best-effort, never blocks the card
        log.warning("rag_index_failed", patient=token, reason=type(e).__name__)
    events = events_repo.query(pid, as_of)
    feats = compute_features(events, as_of, day0)
    task_id = f"nightly-{token}-d{sim_day}"
    thread = f"nightly_patient:{token}:{sim_day}:{hashlib.sha1(task_id.encode()).hexdigest()[:8]}"
    if not force and (existing := ai_repo.pending_card(pid)):
        return {"status": "skipped", "reason": "pending card exists", "approval_id": str(existing)}
    ctx = RunContext(pid, token, as_of, task_id, thread, events, feats, breaker=gov.new_breaker(task_id))
    if live:
        ctx.model = llm.get_model("ORCHESTRATOR")
        agent_model = GovernedChat(gov=llm.get_model("ORCHESTRATOR"), task_id=task_id, patient_id=str(pid))
        sub_model = GovernedChat(gov=llm.get_model("WORKER"), task_id=task_id, patient_id=str(pid))
    else:
        ctx.model = fakes.fake_narrator(feats.cites)
        agent_model = sub_model = fakes.fake_agent_model()
    with checkpointer() as (saver, kind):
        agent = build_orchestrator(agent_model, ctx, checkpointer=saver, subagent_model=sub_model)
        first = run(agent, ctx)
        out = run(agent, ctx, resume="approve") if first["status"] == "interrupted" else first
    tot = ai_repo.task_run_totals(task_id)
    card = ctx.cards["card-1"]["card"] if ctx.cards else None
    return {"status": out["status"], "patient": token, "memory": _memory_summary(mem), "checkpointer": kind, "task_id": task_id,
            "budget_state": gov.state().value, "approvals": out["approvals"], "tier": ai_repo.approval_tier(out["approvals"]),
            "tool_calls": out["tool_calls"], "todos": [t.get("content") for t in out["todos"]],
            "card_source": card.source if card else None, "card_reason": card.reason if card else None,
            "card": card.sentences if card else [], "cut": len(card.cut) if card else 0,
            "tokens_in": tot["tokens_in"], "tokens_out": tot["tokens_out"], "cost_usd": round(tot["cost_usd"], 6)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patient", required=True)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    print(json.dumps(run_patient(a.patient, live=a.live, force=a.force), indent=2, default=str))


if __name__ == "__main__":
    main()
