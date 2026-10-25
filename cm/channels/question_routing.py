"""Lane F: patient question routing. A patient question (Telegram free text or web request) becomes a
doctor request that carries ``data.origin`` (where to reply) and ``data.research`` (a brief for the
doctor, filled in by a background task). Nothing here talks to the patient: the doctor's decision does.

Shapes shared with other lanes (exact):
  data.research = {status: pending|ready|failed, category, priority, brief: [{text, refs}],
                   suggested_reply, confidence, model, cost_usd, reason}
  data.origin   = {channel: telegram|portal, telegram_chat_id?, telegram_message_id?, question_excerpt}
Task: kind ``question_research``, payload ``{approval_id}``, task_id ``qresearch-<approval_id>``.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from uuid import UUID

from cm.channels import tg_text
from cm.core import clock, tasks
from cm.core.logging import get_logger
from cm.router.banned import find_banned
from cm.store import approvals_repo, stream_repo

log = get_logger()
TASK_KIND = "question_research"
EXCERPT_MAX = 80
URGENT = "urgent"
_URGENT_WORDS = {"urgent", "red", "critical", "emergency"}
_HIGH_WORDS = {"high", "amber"}


def task_id(approval_id: UUID | str) -> str:
    return f"qresearch-{approval_id}"


def excerpt(text: str) -> str:
    """Short, patient-safe quote of the question: at most 80 chars, empty when it holds a banned term."""
    t = " ".join(tg_text.normalise(text).split())
    if len(t) > EXCERPT_MAX:
        t = t[: EXCERPT_MAX - 3].rstrip() + "..."
    return "" if find_banned(t) else t


def build_origin(
    channel: str, text: str, *, chat_id: int | None = None, message_id: int | None = None
) -> dict[str, Any]:
    o: dict[str, Any] = {"channel": channel, "question_excerpt": excerpt(text)}
    if chat_id is not None:
        o["telegram_chat_id"] = chat_id
    if message_id is not None:
        o["telegram_message_id"] = message_id
    return o


def blank_research(
    status: str = "pending", *, category: str = "", priority: str = "normal", reason: str = ""
) -> dict[str, Any]:
    return {
        "status": status,
        "category": category,
        "priority": priority,
        "brief": [],
        "suggested_reply": "",
        "confidence": 0.0,
        "model": "",
        "cost_usd": 0.0,
        "reason": reason,
    }


def enqueue_research(approval_id: UUID | str) -> None:
    """Idempotent per approval (same task_id twice is a no-op). Call AFTER the row is committed."""
    tasks.enqueue(
        "agent-runs", task_id(approval_id), {"kind": TASK_KIND, "approval_id": str(approval_id)}
    )


# ---- research backend (lazy; a local stub until cm.agents.question_research exists) ---------------
def _load() -> Any | None:
    try:
        import importlib

        return importlib.import_module("cm.agents.question_research")
    except ImportError:
        return None


def _stub_triage(text: str) -> dict[str, str]:
    cat = tg_text.classify(text)
    return {"category": cat, "priority": URGENT if cat == "danger" else "normal"}


def _field(obj: Any, name: str, default: str) -> str:
    v = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
    return str(v) if v else default


def triage(text: str) -> dict[str, str]:
    mod = _load()
    if mod is None or not hasattr(mod, "triage"):
        return _stub_triage(text)
    try:
        t = mod.triage(text)
    except Exception as exc:  # noqa: BLE001  (triage must never block the doctor notification)
        log.warning("triage failed", error=type(exc).__name__)
        return _stub_triage(text)
    base = _stub_triage(text)
    return {"category": _field(t, "category", base["category"]), "priority": _field(t, "priority", base["priority"])}


def live_allowed() -> bool:
    return os.environ.get("CM_QUESTION_RESEARCH_LIVE", "0").strip() == "1"


def research(token: str, text: str, as_of: datetime, tri: dict[str, str]) -> dict[str, Any]:
    """Run the research agent (fake model unless CM_QUESTION_RESEARCH_LIVE=1). Never raises."""
    mod = _load()
    if mod is None or not hasattr(mod, "research_question"):
        return blank_research("pending", category=tri["category"], priority=tri["priority"], reason="agent_missing")
    live = live_allowed()
    try:
        res = mod.research_question(
            token, text, as_of=as_of, model=None if live else "fake", embed=live
        )
        out = res.as_dict() if hasattr(res, "as_dict") else dict(res)
    except Exception as exc:  # noqa: BLE001
        log.warning("question research failed", error=type(exc).__name__)
        return blank_research("failed", category=tri["category"], priority=tri["priority"], reason=type(exc).__name__)
    return {**blank_research(category=tri["category"], priority=tri["priority"]), **out}


def priority_to_tier(priority: str | None) -> str | None:
    p = (priority or "").lower()
    if p in _URGENT_WORDS:
        return "red"
    if p in _HIGH_WORDS:
        return "amber"
    return None


def run_question_research(approval_id: UUID | str) -> dict[str, Any]:
    """Task handler. Idempotent: a finished brief is not recomputed and the doctor is told once."""
    from cm.api.deps import display_code

    aid = UUID(str(approval_id))
    at = clock.now()
    row = approvals_repo.get(aid, at)
    if row is None:
        return {"status": "missing"}
    data = (row["payload"].get("data") or {})
    cur = data.get("research") or {}
    if cur.get("status") == "ready" and data.get("doctor_notified"):
        return {"status": "duplicate"}
    text = str(data.get("text") or "")
    tri = triage(text)
    res = cur if cur.get("status") == "ready" else research(row.get("patient_token") or "", text, at, tri)
    prio = URGENT if (res.get("priority") or tri["priority"]).lower() in _URGENT_WORDS else None
    tier = priority_to_tier(res.get("priority") or tri["priority"])
    notify = not data.get("doctor_notified")
    approvals_repo.set_research(aid, res, priority=prio, tier=tier, mark_notified=True)
    if notify:
        _tell_doctor(aid, display_code(row.get("patient_token") or ""), res, tri, text)
    return {"status": res.get("status", "pending"), "notified": notify}


def _tell_doctor(aid: UUID, code: str, res: dict[str, Any], tri: dict[str, str], text: str) -> None:
    cat = res.get("category") or tri["category"]
    prio = res.get("priority") or tri["priority"]
    try:
        stream_repo.publish(
            "review",
            {
                "type": "patient_question",
                "kind": "patient_question",
                "ref": str(aid),
                "approval_id": str(aid),
                "patient_code": code,
                "category": cat,
                "priority": prio,
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("stream publish failed", error=type(exc).__name__)
    try:
        import importlib

        mod = importlib.import_module("cm.channels.doctor_notify")
        out = mod.notify_doctor_new_question(
            str(aid), patient_code=code, category=cat, priority=prio, question_excerpt=excerpt(text)
        )
        log.info("doctor email", status=(out or {}).get("status"), reason=(out or {}).get("reason"))
    except ImportError as exc:
        log.warning("doctor email module unavailable", error=str(exc)[:80])
    except Exception as exc:  # noqa: BLE001  (a failed email must not fail the task)
        log.warning("doctor notify failed", error=type(exc).__name__)
