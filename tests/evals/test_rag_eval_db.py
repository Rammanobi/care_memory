"""RAG eval harness, ``--backend db`` (task 4.7): loader, guard, db-vs-memory agreement. caremem_test only.

The non-db tests need no database. The db tests load the PT-0142 log into caremem_test under their own eval tokens
(P-8142 / P-8203), run the real ``build_patient_index`` + ``search_patient_memory`` offline (FakeEmbedder, no LLM,
no network) and prove every row is removed afterwards.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from cm.core.db import transaction
from cm.eval import rag_db
from cm.eval import rag_eval as R

DAYS = (3, 30)
CFGS = [
    dict(R.BASELINE),
    dict(R.BASELINE) | {"mode": "bm25"},
    dict(R.BASELINE) | {"strategy": "dynamic", "mode": "bm25", "rerank": "llm"},
]
TYPES = {
    "DoseCheckin",
    "ContextNote",
    "Dispense",
    "LabResult",
    "SupporterVisit",
    "ReviewDecisionEvent",
}
SOURCES = {
    "telegram",
    "web",
    "supporter",
    "gmail",
    "chemist",
    "lab",
    "system",
    "console",
}


# ----------------------------------------------------------------------------------------- no database
def test_event_mapping_keeps_harness_ids() -> None:
    log = R.build_log()
    pid, cid = uuid4(), uuid4()
    refs: dict[str, str] = {}
    n_notes = 0
    for e in log.of(log.patient):
        for ne, ref in rag_db.to_new_events(e, pid, cid):
            assert ne.type in TYPES and ne.source in SOURCES
            assert ne.occurred_at == e.occurred_at and ne.recorded_at == e.recorded_at
            refs[str(ne.event_id)] = ref
            n_notes += ne.type == "ContextNote" and e.kind == "checkin"
        first = rag_db.to_new_events(e, pid, cid)[0][0]
        assert first.event_id == UUID(e.event_id)  # the main event keeps the harness id
    assert set(refs.values()) == {e.ref for e in log.of(log.patient)}
    assert n_notes > 0  # missed check-ins with a stated reason carry a companion note
    assert len(refs) == len(log.of(log.patient)) + n_notes


def test_db_backend_refuses_any_database_but_caremem_test(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> Any:
        raise AssertionError("the database must not be touched when the guard refuses")

    monkeypatch.setattr("cm.core.db.transaction", boom)
    for name in ("caremem", "", "postgres"):
        monkeypatch.setenv("DB_NAME", name)
        with pytest.raises(rag_db.DbBackendRefused):
            rag_db.require_test_db()
        with pytest.raises(rag_db.DbBackendRefused):
            R.make_ctx(days=(3,), backend="db")


def _report(base: dict[str, float], d: float) -> dict[str, Any]:
    day = {"recall@10": base["r"] + d, "mrr": base["m"] + d, "abstain_acc": base["a"] + d}
    cfg = dict(R.BASELINE)
    row = {"config": cfg, "key": R.config_key(cfg), "days": {"3": day}, "objective": 1.0}
    return {"grid": {"phases": {"ofat": [row]}, "winner": row, "base": cfg}}


def test_compare_backends_reports_signed_and_absolute_differences() -> None:
    mem, db = (
        _report({"r": 0.8, "m": 0.6, "a": 0.9}, 0.0),
        _report({"r": 0.8, "m": 0.6, "a": 0.9}, 0.05),
    )
    c = R.compare_backends(mem, db, tol=0.10)
    assert c["agree"] and c["n_configs"] == 1
    assert c["metrics"]["mrr"]["mean_diff"] == pytest.approx(0.05)
    assert c["baseline"]["days"]["3"]["recall@10"] == {"mem": 0.8, "db": pytest.approx(0.85)}
    far = R.compare_backends(mem, _report({"r": 0.8, "m": 0.6, "a": 0.9}, 0.3), tol=0.10)
    assert not far["agree"] and far["worst"][0]["diff"] == pytest.approx(0.3)
    assert "DISAGREE" in R.render_compare_md(far)


# ----------------------------------------------------------------------------------------- caremem_test
def _loaded_events() -> set[str]:
    with transaction() as c:
        rows = c.execute(
            "SELECT event_id FROM cm.events e JOIN cm.patients p USING (patient_id) JOIN cm.persons per "
            "USING (person_id) WHERE per.token = ANY(%s)",
            (list(rag_db.TOKEN_OF.values()),),
        ).fetchall()
    return {str(r["event_id"]) for r in rows}


@pytest.fixture()
def db_ctx(seeded_db: None):  # noqa: ANN201
    ctx = R.make_ctx(days=DAYS, backend="db")
    yield ctx
    ctx.close()


@pytest.mark.db
def test_load_uses_same_event_ids_and_cleanup_leaves_nothing(seeded_db: None) -> None:
    with transaction() as c:
        before = c.execute("SELECT count(*) AS n FROM cm.patients").fetchone()["n"]
    ctx = R.make_ctx(days=DAYS, backend="db")
    try:
        ids = _loaded_events()
        assert {e.event_id for e in ctx.log.events} <= ids  # same event ids, both patients
        assert ids == set(ctx.db.alias)
        assert ctx.db.n_companions > 0
    finally:
        removed = ctx.close()
    assert removed["events"] == len(ids) and removed["persons"] == 2
    assert not any(rag_db.leftovers().values())
    with transaction() as c:
        assert c.execute("SELECT count(*) AS n FROM cm.patients").fetchone()["n"] == before


@pytest.mark.db
def test_real_index_and_search_per_config_are_clean(db_ctx: R.Ctx) -> None:
    for cfg in CFGS:
        res = R.run_config(db_ctx, cfg, keep_rows=True)
        assert not res["disqualified"], cfg  # no leakage, no foreign chunk, every citation valid
        for m in res["days"].values():
            assert m["temporal_leakage"] == 0 and m["isolation_violations"] == 0
            assert m["citation_validity"] in (None, 1.0)
            assert m["n_chunks"] > 0 and m["recall@10"] is not None
            assert all("db_abstain" in r for r in m["rows"])
    d3 = R.run_config(db_ctx, CFGS[0])["days"]["3"]
    d30 = R.run_config(db_ctx, CFGS[0])["days"]["30"]
    assert d3["n_chunks"] < d30["n_chunks"]  # replayed as_of: day 3 sees less history


@pytest.mark.db
def test_db_hits_map_back_to_gold_event_refs(db_ctx: R.Ctx) -> None:
    cfg = dict(R.BASELINE) | {"mode": "bm25"}
    idx = db_ctx.index(30, cfg)
    q = next(q for q in db_ctx.questions if q.id == "q04-missed-week")
    hits, _, _ = db_ctx.search(idx, db_ctx.plan(q), cfg)
    refs = {e.ref for e in db_ctx.log.of(db_ctx.log.patient, R.as_of_day(30))}
    assert hits and all(set(h.chunk.source) <= refs for h in hits)  # only PT-0142 events at as_of
    assert all(h.chunk.patient == db_ctx.log.patient for h in hits)


@pytest.mark.db
def test_db_and_memory_backends_agree_within_tolerance(db_ctx: R.Ctx) -> None:
    grid = {k: [v] for k, v in R.BASELINE.items()} | {"mode": ["bm25", "hybrid"]}
    mem, db, cmp = R.run_compare(db_ctx, grid, "ofat")
    assert cmp["n_configs"] == 2 and mem["backend"] == "memory" and db["backend"] == "db"
    m = cmp["metrics"]
    # The two backends render events differently (the DB renderer writes its own sentences and drops free text of
    # visits/labs/decisions), so agreement is bounded, not exact. Recall agrees within the harness tolerance; MRR and
    # abstain accuracy within a looser, documented bound (see out/rag_eval/db_backend/compare_*.md).
    assert m["recall@10"]["mean_abs_diff"] <= R.COMPARE_TOL
    assert m["mrr"]["mean_abs_diff"] <= 0.20
    assert m["abstain_acc"]["mean_abs_diff"] <= 0.20
    assert any(rag_db.leftovers().values())  # rows stay loaded until close()
