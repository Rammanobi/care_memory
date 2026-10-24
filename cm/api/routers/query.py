"""Lane G: dashboard Q&A (slice 1: read-only canned answers, no LLM).

Every answer is built from database rows. Every number in the answer text must appear in the rows
cited by its [n] markers; `numbers_verified` reports that check (cm-validator style number guard).
"""
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from fastapi import APIRouter, Depends

from cm.api import readmodels as rm
from cm.api.deps import User, display_code, now, require_roles
from cm.api.portal_models import UiPatient
from cm.contracts.agents import QueryAnswer, QueryIn, ToolCallUsed
from cm.core.db import transaction
from cm.core.logging import get_logger

log = get_logger()

router = APIRouter(prefix="/query", tags=["query"])
CHIPS = [
    "Who needs me first today?",
    "Who has gone quiet?",
    "Why is PT-0142 flagged?",
    "Which patients have a refill gap?",
    "How many requests are waiting?",
    "What changed for PT-0176?",
]
_NUM = re.compile(r"\d+(?:\.\d+)?")


def _call(
    calls: list[ToolCallUsed], tool: str, args: dict[str, Any], rows: list[dict[str, Any]]
) -> int:
    calls.append(
        ToolCallUsed(
            n=len(calls) + 1, tool=tool, args=args, row_count=len(rows), result_preview=rows[:10]
        )
    )
    return len(calls)


def verify_numbers(text: str, calls: list[ToolCallUsed]) -> bool:
    """True when every number in `text` (ignoring [n] markers) appears in the cited rows."""
    known: set[str] = set()
    for c in calls:
        blob = json.dumps(c.result_preview, default=str) + f" {c.row_count} {json.dumps(c.args)}"
        known.update(str(float(n)).rstrip("0").rstrip(".") for n in _NUM.findall(blob))
    nums = _NUM.findall(re.sub(r"\[\d+\]", "", text))
    return all(str(float(n)).rstrip("0").rstrip(".") in known for n in nums)


def _patient_answer(p: UiPatient, calls: list[ToolCallUsed]) -> str:
    n = _call(
        calls,
        "get_patient",
        {"code": p.code},
        [
            {
                "code": p.code,
                "day": p.day,
                "why": p.why,
                "changes": [f"{c.text} {c.ev}" for c in p.changes],
            }
        ],
    )
    parts = [f"{p.code} is on day {p.day}: {p.why.lower()} [{n}]."]
    parts += [f"{c.text}, see {c.ev} [{n}]." for c in p.changes]
    if p.needs_me:
        parts.append(f"A draft for {p.code} is waiting for your review [{n}].")
    return " ".join(parts)


def _list_answer(
    q: str, pts: list[UiPatient], conn: Any, at: Any, calls: list[ToolCallUsed]
) -> str:
    t = q.lower()
    if re.search(r"first|urgent|red|worst|need", t):
        reds = conn.execute(
            "SELECT per.token, a.payload->>'title' AS title FROM cm.approvals a JOIN cm.patients p USING (patient_id) "
            "JOIN cm.persons per ON per.person_id=p.person_id WHERE a.status='pending' AND a.tier='red' "
            "AND a.created_at <= %s ORDER BY a.due_at",
            (at,),
        ).fetchall()
        rows = [{"code": display_code(r["token"]), "title": r["title"]} for r in reds]
        n = _call(calls, "list_pending_approvals", {"tier": "red"}, rows)
        if not rows:
            return f"No red drafts are waiting right now [{n}]."
        return f"{len(rows)} red drafts are waiting, soonest first [{n}]. " + " ".join(
            f"{r['code']}: {r['title']} [{n}]." for r in rows
        )
    if re.search(r"quiet|silent|no reply|no data", t):
        qs = [p for p in pts if p.quiet]
        n = _call(
            calls, "list_patients", {"quiet": True}, [{"code": p.code, "why": p.why} for p in qs]
        )
        return f"{len(qs)} patients are quiet for 3 or more days [{n}]. " + " ".join(
            f"{p.code}: {p.why} [{n}]." for p in qs
        )
    if re.search(r"refill|chemist|supply", t):
        ev = [
            e
            for e in rm.evidence_rows(conn, at)
            if e.kind == "refill" and re.search(r"no refill|left", e.text, re.I)
        ]
        n = _call(
            calls,
            "search_evidence",
            {"kind": "refill"},
            [{"code": e.code, "text": e.text, "ref": e.id} for e in ev],
        )
        return f"{len(ev)} patients have a supply concern [{n}]. " + " ".join(
            f"{e.code}: {e.text} [{n}]." for e in ev
        )
    if re.search(r"request|ask|waiting", t):
        rs = rm.request_rows(conn, at, status="waiting")
        rs = [r for r in rs if not r.archived]
        n = _call(
            calls,
            "list_requests",
            {"status": "waiting"},
            [{"code": r.patient_code, "text": r.text} for r in rs],
        )
        return f"{len(rs)} patient requests are waiting for you [{n}]. " + " ".join(
            f"{r.patient_code} asked: {r.text} [{n}]" for r in rs
        )
    if re.search(r"approv|draft", t):
        c = conn.execute(
            "SELECT count(*) AS n FROM cm.approvals WHERE status='pending' AND created_at <= %s "
            "AND COALESCE(payload->>'subkind','') <> 'patient_request'",
            (at,),
        ).fetchone()["n"]
        n = _call(calls, "count_pending_approvals", {}, [{"pending": c}])
        return f"{c} drafts are waiting for approval [{n}]."
    n = _call(calls, "count_patients", {}, [{"patients": len(pts)}])
    return f"I can answer from the {len(pts)} patients on the list [{n}]. Try one of the suggested questions."



# ---------------------------------------------------------------- LLM path (WORKER model + read-only tools)
SYSTEM = (
    "You answer a doctor's question about their patient list using ONLY the tools. Be brief and plain. "
    "After every fact write the tool-result marker like [1] given in the tool output. Never state a number "
    "that is not in a tool result. No advice, no diagnosis."
)
MAX_STEPS = 4


def _worker_chat() -> Any:
    """The governed WORKER model as a chat model. Tests replace this with a scripted fake."""
    from cm.agents.governed_chat import GovernedChat
    from cm.core import llm

    return GovernedChat(gov=llm.get_model("WORKER"), task_id="ask-box", task_type="eval")


def llm_available() -> bool:
    """True when a key is set for the WORKER provider and the governor is not RED."""
    from cm.core import llm

    if "PYTEST_CURRENT_TEST" in os.environ:  # the suite never makes live calls; tests patch this function
        return False
    try:
        spec = llm.resolve_spec("WORKER") or ""
        key = "DEEPSEEK_API_KEY" if spec.startswith("deepseek:") else "OPENAI_API_KEY"
        return bool(os.environ.get(key)) and not llm.get_governor().policy().template_only
    except Exception:  # noqa: BLE001
        return False


def _tools(pts: list[UiPatient], pending: list[dict[str, Any]], calls: list[ToolCallUsed]) -> list[Any]:
    from langchain_core.tools import StructuredTool
    from pydantic import create_model

    def finish(tool: str, args: dict[str, Any], rows: list[dict[str, Any]]) -> str:
        n = _call(calls, tool, args, rows)
        return json.dumps({"marker": f"[{n}]", "row_count": len(rows), "rows": rows[:10]}, default=str)

    def list_patients(quiet: bool | None = None) -> str:
        sel = [p for p in pts if quiet is None or p.quiet == quiet]
        rows = [{"code": p.code, "day": p.day, "why": p.why, "quiet": p.quiet, "needs_me": p.needs_me} for p in sel]
        return finish("list_patients", {"quiet": quiet}, rows)

    def get_patient(code: str) -> str:
        p = next((x for x in pts if x.code == code.upper()), None)
        rows = [{"code": p.code, "day": p.day, "why": p.why, "changes": [f"{c.text} {c.ev}" for c in p.changes]}] if p else []
        return finish("get_patient", {"code": code.upper()}, rows)

    def list_pending_approvals(tier: str | None = None) -> str:
        rows = [r for r in pending if tier is None or r["tier"] == tier]
        return finish("list_pending_approvals", {"tier": tier}, rows)

    specs = [(list_patients, create_model("A1", quiet=(bool | None, None)), "Patients with day, reason, quiet flag."),
             (get_patient, create_model("A2", code=(str, ...)), "One patient by code like PT-0142."),
             (list_pending_approvals, create_model("A3", tier=(str | None, None)), "Pending drafts; tier red/amber/green.")]
    return [StructuredTool.from_function(f, name=f.__name__, description=d, args_schema=a) for f, a, d in specs]


def llm_answer(question: str, pts: list[UiPatient], pending: list[dict[str, Any]], calls: list[ToolCallUsed]) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

    from cm.core.tokenize import tokenize

    tools = _tools(pts, pending, calls)
    by_name = {t.name: t for t in tools}
    model = _worker_chat().bind_tools(tools)
    msgs: list[Any] = [SystemMessage(content=SYSTEM), HumanMessage(content=tokenize(question))]
    for _ in range(MAX_STEPS):
        ai = model.invoke(msgs)
        msgs.append(ai)
        if not ai.tool_calls:
            text = ai.content if isinstance(ai.content, str) else json.dumps(ai.content)
            if not text.strip():
                raise ValueError("empty answer")
            return text.strip()
        for tc in ai.tool_calls:
            out = by_name[tc["name"]].invoke(tc["args"]) if tc["name"] in by_name else "unknown tool"
            msgs.append(ToolMessage(content=out, tool_call_id=tc["id"]))
    raise ValueError("too many tool steps")


def _pending_rows(conn: Any, at: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT per.token, a.tier, a.payload->>'title' AS title FROM cm.approvals a JOIN cm.patients p USING (patient_id) "
        "JOIN cm.persons per ON per.person_id=p.person_id WHERE a.status='pending' AND a.created_at <= %s "
        "AND COALESCE(a.payload->>'subkind','') <> 'patient_request' ORDER BY a.due_at",
        (at,),
    ).fetchall()
    return [{"code": display_code(r["token"]), "tier": r["tier"], "title": r["title"]} for r in rows]


@router.post("", response_model=QueryAnswer)
def ask(
    body: QueryIn, _: User = Depends(require_roles("doctor", "sts", "dto", "admin"))
) -> QueryAnswer:
    t0 = time.monotonic()
    at = now()
    calls: list[ToolCallUsed] = []
    with transaction() as conn:
        pts = rm.ui_patients(conn, at)
        pending = _pending_rows(conn, at) if llm_available() else []
        m = re.search(r"PT-\d{4}", body.question, re.I)
        hit = next((p for p in pts if m and p.code == m.group(0).upper()), None)
        canned = lambda: (  # noqa: E731
            _patient_answer(hit, calls) if hit else _list_answer(body.question, pts, conn, at, calls)
        )
        text = None
        if llm_available():
            try:
                text = llm_answer(body.question, pts, pending, calls)
                if not calls or not verify_numbers(text, calls):
                    raise ValueError("answer not grounded")
            except Exception as e:  # noqa: BLE001  (any model problem: canned answer, same shape)
                log.warning("ask_llm_fallback", reason=type(e).__name__)
                calls.clear()
                text = None
        if text is None:
            text = canned()
    return QueryAnswer(
        answer_text=text,
        tool_calls_used=calls,
        as_of=rm.sim_date(at),
        numbers_verified=verify_numbers(text, calls),
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


@router.get("/suggestions", response_model=list[str])
def suggestions(_: User = Depends(require_roles("doctor", "sts", "dto", "admin"))) -> list[str]:
    return CHIPS
