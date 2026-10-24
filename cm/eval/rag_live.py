"""Lane J: live answer quality for the patient-memory Ask box (docs/design/RAG_EVAL_PLAN.md, live mode).

``python -m cm.eval.rag_live --days 3,30,60 --embedder openai`` (also reached by ``rag_eval --live``).

The answer comes from ``cm.api.routers.query.compose_answer``: the same function the Ask box calls, with the same
pre-abstain rules, prompt, temperature 0, cite-or-cut and output guard. Retrieval mirrors ``cm.tools.memory_search``
on the in-memory index: event chunks plus closed-week cards (strategy ``dynamic``), the small-corpus switch (at most
``SMALL_CORPUS`` live chunks: send all, oldest first), otherwise hybrid top 12 with the two best chunks as key evidence.
Pattern questions also get the weekly-card quota of ``cm.rag.retrieve.with_rollup_quota``. Not mirrored: MMR, the 3-per-day cap, retrieval-side abstain and daily cards (they exist only in the DB index).

Scoring: abstain accuracy against the generated gold (a refusal counts as a non-answer), groundedness = share of the
model draft's sentences that survive cite-or-cut, answer correctness for questions with an expected fact, and a JUDGE
rubric run only on answered cases against the chunks the answer cites. Model replies (subject and judge) are cached
on disk by prompt hash, so ``--only`` and ``--rescore`` re-score without new spend. Cost is the governor estimate
(pessimistic default prices unless CM_PRICE_TABLE_JSON names the model). Only totals are printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from cm.eval import rag_eval as R

LIVE_CFG: dict[str, Any] = {
    "size": 256,
    "overlap": 50,
    "strategy": "dynamic",  # event chunks + closed-week cards, like the production index
    "mode": "hybrid",
    "rerank": "none",  # owner ruling: no rerank in the Ask box
    "top_k": 12,  # cm.tools.memory_search.DEFAULT_K
}
JUDGE_MAX_TOKENS = 300
JUDGE_RETRY_TOKENS = 900
CACHE_NAME = "live_cache.json"
TE_WEEKDAYS = ("సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం", "ఆదివారం")
MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
TE_MONTHS = (
    "జనవరి",
    "ఫిబ్రవరి",
    "మార్చి",
    "ఏప్రిల్",
    "మే",
    "జూన్",
    "జూలై",
    "ఆగస్టు",
    "సెప్టెంబర్",
    "అక్టోబర్",
    "నవంబర్",
    "డిసెంబర్",
)


@dataclass
class AskHit:
    """The attribute shape the Ask-box composer reads (cm.tools.memory_search.ChunkHit subset)."""

    ref: str
    text: str
    date: str
    kind: str
    author_role: str = "record"
    numbers: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime | None = None
    recorded_at: datetime | None = None


class NotCached(RuntimeError):
    pass


class ReplyCache:
    """Model replies by prompt hash, persisted as JSON. Offline mode raises NotCached instead of calling."""

    def __init__(self, path: Path | None, offline: bool = False) -> None:
        self.path, self.offline = path, offline
        self.data: dict[str, str] = {}
        if path and path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
        self.hits = self.misses = 0

    @staticmethod
    def key(role: str, messages: Any, kw: dict[str, Any]) -> str:
        from cm.core.llm import _text_of

        raw = f"{role}\x1f{_text_of(messages)}\x1f{json.dumps(kw, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def call(self, role: str, inner: Any, messages: Any, task_id: str, **kw: Any) -> Any:
        k = self.key(role, messages, kw)
        if k in self.data:
            self.hits += 1
            return SimpleNamespace(content=self.data[k])
        if self.offline or inner is None:
            raise NotCached(task_id)
        out = inner.invoke(messages, task_id=task_id, task_type="eval", **kw)
        self.misses += 1
        c = out.content if isinstance(out.content, str) else json.dumps(out.content)
        self.data[k] = c
        return SimpleNamespace(content=c)

    def flush(self) -> None:
        if self.path and self.misses:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")


class EvalChat:
    """``invoke(messages)`` like the Ask box's chat model, routed through the capped eval governor and the cache."""

    def __init__(self, inner: Any, cache: ReplyCache, task_id: str) -> None:
        self.inner, self.cache, self.task_id = inner, cache, task_id

    def invoke(self, messages: Any, **_: Any) -> Any:
        return self.cache.call("WORKER", self.inner, messages, self.task_id, temperature=0)


# ------------------------------------------------------------------------------------------- retrieval
def ask_hits(
    ctx: R.Ctx, idx: R.MemIndex, plan: R.QueryPlan
) -> tuple[list[AskHit], list[str], dict[str, int]]:
    """Production-shaped context: all chunks for a small corpus, else hybrid top-k; date ascending; key refs."""
    from cm.tools.memory_search import KEY_EVIDENCE, SMALL_CORPUS

    kinds: dict[str, int] = {}
    for c in idx.chunks:
        kinds[c.kind] = kinds.get(c.kind, 0) + 1
    if len(idx.chunks) <= SMALL_CORPUS:
        chosen, key = list(idx.chunks), []
    else:
        from cm.rag.retrieve import with_rollup_quota

        full, _, _ = R.search_mem(idx, plan, dict(LIVE_CFG, top_k=len(idx.chunks)), ctx.emb, ctx.api)
        hits = full[: LIVE_CFG["top_k"]]
        if plan.pattern:  # the production pattern-question rollup quota (cm.rag.retrieve.with_rollup_quota)
            seen = {h.ref for h in full}
            rest = sorted(
                (R.Hit(c, 0.0) for c in idx.chunks if c.kind == "weekly" and c.ref not in seen),
                key=lambda h: -h.chunk.occurred_at.timestamp(),
            )
            hits = with_rollup_quota(hits, full[LIVE_CFG["top_k"] :] + rest, lambda h: h.chunk.kind)
        chosen = [h.chunk for h in hits]
        key = [h.ref for h in sorted(hits, key=lambda h: -h.score)[:KEY_EVIDENCE]]
    chosen.sort(key=lambda c: (c.occurred_at, c.ref))
    out = [
        AskHit(
            c.ref,
            c.text,
            c.occurred_at.date().isoformat(),
            c.kind,
            occurred_at=c.occurred_at,
            recorded_at=c.recorded_at,
        )
        for c in chosen
    ]
    return out, key, kinds


# ------------------------------------------------------------------------------------------- scoring
def mentions(expected: str, text: str) -> bool:
    """Expected fact present in English or Telugu: a weekday name, or an ISO date in ISO / 'D Month' form."""
    t = text.lower()
    if expected in R.WEEKDAYS:
        return expected.lower() in t or TE_WEEKDAYS[R.WEEKDAYS.index(expected)] in text
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", expected)
    if m:
        d, mon = int(m.group(3)), int(m.group(2)) - 1
        forms = [
            expected,
            f"{d} {MONTHS[mon]}",
            f"{MONTHS[mon]} {d}",
            f"{d} {MONTHS[mon][:3]}",
            f"{MONTHS[mon][:3]} {d}",
            f"{d} {TE_MONTHS[mon]}",
            f"{TE_MONTHS[mon]} {d}",
        ]
        return any(re.search(rf"(?<!\d){re.escape(f.lower())}(?!\d)", t) for f in forms)
    return expected.lower() in t


def _judge(
    jm: Any, cache: ReplyCache, q: R.Question, hits: list[AskHit], text: str, tid: str
) -> dict[str, Any]:
    from cm.core.tokenize import tokenize
    from cm.eval import ai_eval as ae

    cited = set(re.findall(r"D-[0-9a-f]{8}", text))
    rows = [{"ref": h.ref, "date": h.date, "text": h.text} for h in hits if h.ref in cited]
    prompt = ae.ASK_RUBRIC.format(
        question=q.question, rows=json.dumps(rows, ensure_ascii=False), answer=text
    )
    for cap in (JUDGE_MAX_TOKENS, JUDGE_RETRY_TOKENS):  # retry once with more room when the reply was cut
        try:
            raw = cache.call("JUDGE", jm, tokenize(prompt), tid, max_tokens=cap, temperature=0)
        except NotCached:
            if cap == JUDGE_MAX_TOKENS:
                raise
            return {"error": "JSONDecodeError"}  # rescore mode: the longer retry was never paid for
        except Exception as e:  # noqa: BLE001
            return {"error": type(e).__name__}
        try:
            return ae._json_of(raw)  # noqa: SLF001
        except ValueError:  # cut inside "note": keep the verdicts when all four are present
            pat = rf'"({"|".join(JUDGE_KEYS)})"\s*:\s*(true|false)'
            got = {k: v == "true" for k, v in re.findall(pat, raw.content)}
            if len(got) == len(JUDGE_KEYS):
                return got | {"note": "(note cut by token cap)"}
    return {"error": "JSONDecodeError"}


JUDGE_KEYS = ("grounded", "no_advice", "resisted_injection", "no_pii")


def negative_ok_ids() -> set[str]:
    """Question ids marked ``negative_ok`` in fixtures/rag_evals/questions.json."""
    data = json.loads((R.FIXTURES / "questions.json").read_text(encoding="utf-8"))
    return {q["id"] for q in data["questions"] if q.get("negative_ok")}


def live_one(
    ctx: R.Ctx,
    idx: R.MemIndex,
    q: R.Question,
    d: int,
    model: Any,
    jm: Any,
    cache: ReplyCache,
    judge: bool = True,
) -> dict[str, Any]:
    from cm.api.routers.query import compose_answer

    plan = ctx.plan(q)
    hits, key, kinds = ask_hits(ctx, idx, plan)
    g = ctx.gold[str(d)][q.id]
    row: dict[str, Any] = {
        "day": d,
        "q": q.id,
        "lang": q.lang,
        "kind": q.kind,
        "expect_abstain": g["expect_abstain"],
        "n_ctx": len(hits),
    }
    chat = EvalChat(model, cache, f"rag-eval-live-{q.id}-d{d}")
    out = compose_answer(ctx.log.patient, d, q.question, hits, key, kinds, use_llm=True, chat=chat)
    non_answer = out.abstained or out.refusal is not None
    cited = [] if non_answer else re.findall(r"D-[0-9a-f]{8}", out.text)
    ans = R.Answer(out.text, [], non_answer, cited, "askbox")
    row |= {
        "answer": out.text,
        "abstained": out.abstained,
        "why": out.why or (f"refused:{out.refusal}" if out.refusal else ""),
        # a yes/no "has X happened?" question with no gold event may also be answered "no" from the record
        # (e.g. weekly cards saying 0 days without check-in); the cited sentence still has to survive cite-or-cut
        "abstain_ok": non_answer == g["expect_abstain"]
        or (g["expect_abstain"] and q.id in negative_ok_ids() and bool(cited)),
        "grounded": round(out.kept / out.draft, 4) if out.draft and not out.abstained else None,
        "citation_validity": R.citation_validity(ans, idx, ctx.log),
        "leak": sum(1 for h in hits if h.recorded_at and h.recorded_at > idx.as_of),
    }
    if g["expected"] and not non_answer and q.kind in ("pattern", "event"):
        row["answer_correct"] = mentions(g["expected"], out.text)
    if judge and not non_answer:
        try:
            j = _judge(jm, cache, q, hits, out.text, f"ai-eval-judge-rag-{q.id}-d{d}")
        except NotCached:  # rescore mode and this answer was never judged (e.g. a --no-judge run)
            j = {"error": "not_judged"}
        if "error" in j:  # a judge failure is reported, not counted as an answer failure
            row["judge_error"] = j["error"]
        else:
            row["judge_pass"] = all(j.get(k) is not False for k in JUDGE_KEYS)
            row["judge_note"] = str(j.get("note", ""))[:140]
    return row


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    run = [r for r in rows if "skipped" not in r]
    return {
        "n": len(rows),
        "run": len(run),
        "skipped": len(rows) - len(run),
        "answered": sum(1 for r in run if r.get("citation_validity") is not None),
        "abstain_acc": R._avg([float(r["abstain_ok"]) for r in run]),  # noqa: SLF001
        "groundedness": R._avg([r["grounded"] for r in run]),  # noqa: SLF001
        "judge_pass": R._avg([float(r["judge_pass"]) for r in run if "judge_pass" in r]),  # noqa: SLF001
        "n_judged": sum(1 for r in run if "judge_pass" in r),
        "judge_errors": sum(1 for r in run if "judge_error" in r),
        "answer_correct": R._avg(
            [float(r["answer_correct"]) for r in run if "answer_correct" in r]
        ),  # noqa: SLF001
        "citation_validity": R._avg([r["citation_validity"] for r in run]),  # noqa: SLF001
        "leak": sum(r["leak"] for r in run),
    }


def run_live(
    ctx: R.Ctx,
    *,
    cap: float = R.ANSWER_CAP_USD,
    only: set[str] | None = None,
    offline: bool = False,
    cache_dir: Path = R.OUT_DIR,
    judge: bool = True,
) -> dict[str, Any]:
    from cm.core.budget import BudgetExceeded
    from cm.core.llm import GovernedModel
    from cm.eval import ai_eval as ae

    cache = ReplyCache(cache_dir / CACHE_NAME, offline=offline)
    model = jm = gov = None
    if not offline:
        env = ae.live_env()
        gov = ae.live_governor(cap)
        model, jm = (
            GovernedModel("WORKER", governor=gov, env=env),
            GovernedModel("JUDGE", governor=gov, env=env),
        )
    rows: list[dict[str, Any]] = []
    per_day_cost: dict[str, float] = {}
    for d in ctx.days:
        idx = ctx.index(d, LIVE_CFG)
        before = gov.store.total_cost() if gov else 0.0
        for q in ctx.questions:
            if only and q.id not in only:
                continue
            try:
                rows.append(live_one(ctx, idx, q, d, model, jm, cache, judge))
            except NotCached:
                rows.append({"day": d, "q": q.id, "skipped": "not_cached"})
            except BudgetExceeded:
                rows.append({"day": d, "q": q.id, "skipped": "budget_cap"})
            except Exception as e:  # noqa: BLE001 (TemplateOnlyMode when the governor turns RED, provider errors)
                rows.append({"day": d, "q": q.id, "skipped": type(e).__name__})
        per_day_cost[str(d)] = round((gov.store.total_cost() if gov else 0.0) - before, 4)
        cache.flush()
    cost: dict[str, Any] = {
        "cap_usd": cap,
        "new_usd": 0.0,
        "cache_hits": cache.hits,
        "new_calls": cache.misses,
        "per_day_usd": per_day_cost,
    }
    if gov is not None:
        st = gov.store
        cost |= {
            "new_usd": round(st.total_cost(), 4),
            "subject_usd": round(st.by_kind.get("subject", 0.0), 4),
            "judge_usd": round(st.by_kind.get("judge", 0.0), 4),
            "tokens_in": st.tokens_in,
            "tokens_out": st.tokens_out,
            "price_source": "CM_PRICE_TABLE_JSON"
            if ae.spec_priced(ae.live_env())
            else "governor default (pessimistic)",
        }
    by_day = {str(d): summarize([r for r in rows if r["day"] == d]) for d in ctx.days}
    return {
        "config": LIVE_CFG,
        "cost": cost,
        "rows": rows,
        "by_day": by_day,
        "summary": summarize(rows),
    }


# ------------------------------------------------------------------------------------------- report + CLI
COLS = (
    "run",
    "skipped",
    "abstain_acc",
    "groundedness",
    "judge_pass",
    "n_judged",
    "answer_correct",
    "citation_validity",
    "leak",
)


def render_md(rep: dict[str, Any]) -> str:
    lines = [
        "| as_of day | " + " | ".join(COLS) + " | new cost USD |",
        "|---" * (len(COLS) + 2) + "|",
    ]
    for d, m in rep["by_day"].items():
        lines.append(
            f"| {d} | "
            + " | ".join(R._fmt(m.get(c)) for c in COLS)  # noqa: SLF001
            + f" | {rep['cost']['per_day_usd'].get(d, 0.0):.4f} |"
        )
    m = rep["summary"]
    lines.append(
        "| all | "
        + " | ".join(R._fmt(m.get(c)) for c in COLS)
        + f" | {rep['cost']['new_usd']:.4f} |"
    )  # noqa: SLF001
    lines += [
        "",
        "| day | question | expect | got | why | grounded | correct | judge | answer (first 120 chars) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rep["rows"]:
        if "skipped" in r:
            lines.append(f"| {r['day']} | {r['q']} | | skipped: {r['skipped']} | | | | | |")
            continue
        exp = "abstain" if r["expect_abstain"] else "answer"
        got = (
            "abstain"
            if r["abstained"]
            else ("refused" if r["why"].startswith("refused") else "answer")
        )
        ans = r["answer"][:120].replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {r['day']} | {r['q']} | {exp} | {got} | {r['why']} | {R._fmt(r['grounded'])} | "  # noqa: SLF001
            f"{R._fmt(r.get('answer_correct'))} | {R._fmt(r.get('judge_pass'))} | {ans} |"
        )  # noqa: SLF001
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from cm.core.config import load_dotenv

    load_dotenv()
    ap = argparse.ArgumentParser(
        prog="python -m cm.eval.rag_live", description=__doc__.split("\n\n")[0]
    )
    ap.add_argument("--patient", default="PT-0142")
    ap.add_argument("--days", default="3,30,60")
    ap.add_argument("--seed", type=int, default=R.SIM_SEED)
    ap.add_argument("--embedder", choices=("fake", "openai"), default="fake")
    ap.add_argument("--only", default="", help="comma-separated question ids to (re-)run")
    ap.add_argument("--rescore", action="store_true", help="cached replies only: no provider calls")
    ap.add_argument(
        "--cap", type=float, default=R.ANSWER_CAP_USD, help="governor cap for this run (max 1.00)"
    )
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--out", default=str(R.OUT_DIR))
    a = ap.parse_args(argv)
    out = Path(a.out)
    ctx = R.make_ctx(
        a.patient, [int(x) for x in a.days.split(",") if x.strip()], a.seed, a.embedder, out
    )
    only = {x.strip() for x in a.only.split(",") if x.strip()} or None
    rep = run_live(
        ctx,
        cap=min(a.cap, R.ANSWER_CAP_USD),
        only=only,
        offline=a.rescore,
        cache_dir=out,
        judge=not a.no_judge,
    )
    ctx.emb.flush()
    stem = f"rag_live_{a.patient}_seed{a.seed}"
    (out / f"{stem}.json").write_text(
        json.dumps(rep, indent=1, ensure_ascii=False, default=str), encoding="utf-8"
    )
    (out / f"{stem}.md").write_text(
        f"# RAG live answers {a.patient}\n\n{render_md(rep)}\n", encoding="utf-8"
    )
    for d, m in rep["by_day"].items():
        print(f"day {d}: " + ", ".join(f"{c} {R._fmt(m.get(c))}" for c in COLS))  # noqa: SLF001
    c = rep["cost"]
    print(
        f"cost: new ${c['new_usd']:.4f} (cap ${c['cap_usd']:.2f}), new calls {c['new_calls']}, cache hits "
        f"{c['cache_hits']}, embedding ${ctx.emb.stats()['usd']:.4f}"
    )
    print(f"wrote {out / (stem + '.json')} and .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
