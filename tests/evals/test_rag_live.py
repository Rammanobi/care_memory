"""Live answer mode wiring, offline (stub models, no network): production composer, pre-abstain rules, scoring."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any

import pytest

from cm.api.routers import query as Q
from cm.eval import rag_eval as R
from cm.eval import rag_live as L
from cm.tools.memory_search import is_pattern_question


@pytest.fixture(scope="module")
def ctx() -> R.Ctx:
    return R.make_ctx("PT-0142", (3, 30, 60), embedder="fake")


class Inner:
    """Stands in for GovernedModel: answers with the first chunk ref it is shown (or a fixed reply)."""

    def __init__(self, reply: str | None = None) -> None:
        self.reply, self.calls, self.kw = reply, 0, {}

    def invoke(self, messages: Any, *, task_id: str, task_type: str, **kw: Any) -> Any:
        self.calls += 1
        self.kw = kw
        if self.reply is not None:
            return SimpleNamespace(content=self.reply)
        ref = re.search(r"\[(D-[0-9a-f]{8})\]", messages[-1].content).group(1)
        return SimpleNamespace(content=f"Seen in the record [{ref}]. Unsupported line.")


class Judge:
    def __init__(self) -> None:
        self.prompt = ""

    def invoke(self, prompt: Any, **_: Any) -> Any:
        self.prompt = prompt
        return SimpleNamespace(content=json.dumps({k: True for k in L.JUDGE_KEYS} | {"note": "ok"}))


def _q(ctx: R.Ctx, qid: str) -> R.Question:
    return next(q for q in ctx.questions if q.id == qid)


def _one(ctx: R.Ctx, qid: str, day: int, inner: Inner, judge: Judge | None = None) -> dict[str, Any]:
    idx = ctx.index(day, L.LIVE_CFG)
    return L.live_one(ctx, idx, _q(ctx, qid), day, inner, judge or Judge(), L.ReplyCache(None))


def test_day3_pattern_question_abstains_before_any_model_call(ctx: R.Ctx) -> None:
    inner = Inner()
    for qid in ("q01-weekday", "t01-weekday"):  # English and Telugu pattern questions
        row = _one(ctx, qid, 3, inner)
        assert row["abstained"] and row["why"] == "pattern_too_early" and row["abstain_ok"]
    assert inner.calls == 0


def test_other_patient_question_abstains(ctx: R.Ctx) -> None:
    row = _one(ctx, "q16-adv-foreign", 30, Inner())
    assert row["why"] == "other_patient" and row["abstain_ok"]


def test_answer_goes_through_askbox_cut_and_judge_sees_only_cited_chunks(ctx: R.Ctx) -> None:
    inner, judge = Inner(), Judge()
    row = _one(ctx, "q12-medicines", 30, inner, judge)
    assert not row["abstained"] and row["grounded"] == 0.5  # one of two draft sentences survives cite-or-cut
    assert row["citation_validity"] == 1.0 and row["judge_pass"] is True
    assert inner.kw == {"temperature": 0}
    assert len(set(re.findall(r"D-[0-9a-f]{8}", judge.prompt))) == 1


def test_model_not_in_record_is_an_abstention(ctx: R.Ctx) -> None:
    row = _one(ctx, "q08-lab", 3, Inner(Q.NOT_IN_RECORD))
    assert row["abstained"] and row["why"] == "model" and row["abstain_ok"] and "judge_pass" not in row


def test_small_corpus_sends_all_chunks_large_corpus_top_k(ctx: R.Ctx) -> None:
    q = _q(ctx, "q03-refill")
    small = ctx.index(30, L.LIVE_CFG)
    hits, key, kinds = L.ask_hits(ctx, small, ctx.plan(q))
    assert len(hits) == len(small.chunks) and key == [] and kinds.get("weekly")
    big = ctx.index(60, L.LIVE_CFG)
    hits, key, _ = L.ask_hits(ctx, big, ctx.plan(q))
    assert len(big.chunks) > 60 and len(hits) == L.LIVE_CFG["top_k"] and len(key) == 2
    assert [h.date for h in hits] == sorted(h.date for h in hits)


def test_rescore_mode_never_calls_a_model(ctx: R.Ctx) -> None:
    idx = ctx.index(30, L.LIVE_CFG)
    with pytest.raises(L.NotCached):
        L.live_one(ctx, idx, _q(ctx, "q03-refill"), 30, None, None, L.ReplyCache(None, offline=True))


def test_mentions_accepts_english_telugu_and_date_forms() -> None:
    assert L.mentions("Tuesday", "missed on Tuesday") and L.mentions("Tuesday", "మంగళవారం మిస్")
    assert L.mentions("2026-02-21", "collected on 21 February") and L.mentions("2026-02-21", "on 2026-02-21న")
    assert not L.mentions("2026-02-21", "collected on 1 February")


def test_telugu_pattern_questions_are_detected() -> None:
    assert is_pattern_question("రోగి సాధారణంగా ఏ రోజు మందు మిస్ అవుతారు?")
    assert not is_pattern_question("చివరి రీఫిల్ ఎప్పుడు జరిగింది?")


def test_numbers_inside_iso_dates_and_hyphenated_words_count_as_evidence() -> None:
    hit = L.AskHit("D-aaaaaaaa", "2026-01-29 Thu, chemist: refill collected: 14-day supply.", "2026-01-29", "event")
    assert Q.cut_to_cited("Collected on 29 January, a 14 day supply [D-aaaaaaaa].", [hit])
    assert Q.cut_to_cited("Collected 15 days of supply [D-aaaaaaaa].", [hit]) == []


def test_compose_answer_is_shared_by_route_and_eval() -> None:
    import inspect

    assert "compose_answer(" in inspect.getsource(Q.rag_answer)
    assert "compose_answer(" in inspect.getsource(L.live_one)
