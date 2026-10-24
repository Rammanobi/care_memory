"""Lane J: database side of the RAG eval harness (``rag_eval --backend db``, task 4.7 of add-patient-rag).

Loads the harness's deterministic event log into ``caremem_test`` as real ``cm.events`` rows (same event ids), builds
the real index (``cm.rag.index.build_patient_index``) and searches it (``cm.rag.retrieve.search_patient_memory``),
and removes every row it wrote when it is done.

Safety:
* ``require_test_db`` refuses to do anything unless ``DB_NAME`` is ``caremem_test`` AND the connected database
  reports that name. The live database is never touched.
* The harness patients get their OWN tokens (``P-8142`` / ``P-8203``) and deterministic person ids, so nothing the
  seed or other tests created is ever read, changed or deleted. ``cleanup`` deletes only those rows.
* No LLM and no network: the reranker is replaced by the harness's offline stand-in while searching.

Fidelity notes (report these, do not hide them): the DB renderer (``cm.rag.render``) writes its own sentences, drops
lab values, tablet counts and free text of supporter visits/labs/decisions, and has no event type for
"no check-in" notes, so a ContextNote with origin ``system`` carries those. A check-in that carries free text in the
harness (a stated reason or reply) becomes TWO DB events: the DoseCheckin (harness id) and a companion ContextNote
(derived id) holding the text. ``Session.alias`` maps both ids back to the harness ref, so gold stays "same ids".
"""

from __future__ import annotations

import contextlib
import os
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from unittest import mock
from uuid import UUID

from cm.core.ids import det_id
from cm.store import consent as consent_repo
from cm.store import events_repo, search_repo

TEST_DB = "caremem_test"
TOKEN_OF = {"main": "P-8142", "foreign": "P-8203"}  # eval-only tokens, never used by the seed
_KEY = "rag-eval-db"
_REASON = re.compile(r"^[^;]*; (.*)$", re.S)

# harness channel -> events.source
_SOURCE = {
    "Telegram": "telegram",
    "Web app": "web",
    "Clinic": "console",
    "Console": "console",
    "Chemist feed": "chemist",
    "Supporter": "supporter",
    "Gmail": "gmail",
    "Lab feed": "lab",
    "System": "system",
}
_NOTE_ORIGIN = {  # harness kind -> ContextNote payload.origin
    "medicine": "doctor",
    "document": "doctor",
    "email": "doctor",
    "note": "doctor",
    "symptom": "patient_text",
    "injection": "patient_text",
    "refill_gap": "system",
    "quiet": "system",
}


class IndexLost(RuntimeError):
    """The index rows changed under us (another process re-seeded the shared test database)."""


def _transient() -> tuple[type[BaseException], ...]:
    import psycopg

    return (psycopg.OperationalError, psycopg.errors.IntegrityError, LookupError, IndexLost)


class DbBackendRefused(RuntimeError):
    """Raised when the DB backend is asked to run against anything but caremem_test."""


def require_test_db() -> None:
    """Hard guard: env name AND the live connection must both say caremem_test."""
    name = os.environ.get("DB_NAME", "")
    if name != TEST_DB:
        raise DbBackendRefused(
            f"--backend db refused: DB_NAME is {name or '<unset>'!r}, it must be {TEST_DB!r}. "
            f"Run with DB_NAME={TEST_DB} (the live database is never used)."
        )
    from cm.core.db import transaction

    with transaction() as c:
        actual = c.execute("SELECT current_database() AS d").fetchone()["d"]
    if actual != TEST_DB:
        raise DbBackendRefused(f"--backend db refused: connected to {actual!r}, not {TEST_DB!r}")


def _event_source(channel: str, kind: str) -> str:
    return _SOURCE.get(channel, "system" if kind in ("quiet", "refill_gap") else "console")


def _iso(ev: Any) -> str:
    return ev.occurred_at.date().isoformat()


def _payload(ev: Any) -> tuple[str, dict[str, Any], str]:
    """(events.type, payload, reporter_mode) for one harness event."""
    k = ev.kind
    if k == "checkin":
        return (
            "DoseCheckin",
            {"status": ev.meta.get("status", "taken"), "for_date": _iso(ev)},
            "self",
        )
    if k == "refill":
        return "Dispense", {"days_supply": 14}, "record"
    if k == "household":
        return (
            "SupporterVisit",
            {"visit_kind": "family_screen", "visit_date": _iso(ev)},
            "witnessed",
        )
    if k == "supporter" and "travelling" not in ev.text:
        return "SupporterVisit", {"mode": "witnessed", "visit_date": _iso(ev)}, "witnessed"
    if k == "decision":
        return (
            "ReviewDecisionEvent",
            {"kind": "decision", "action": "approve", "reason": ev.text},
            "record",
        )
    if k == "lab":
        return "LabResult", {"report_date": _iso(ev)}, "record"
    origin = "supporter_text" if k == "supporter" else _NOTE_ORIGIN.get(k, "doctor")
    return "ContextNote", {"origin": origin, "text_tokenised": ev.text}, "record"


def to_new_events(
    ev: Any, patient_id: UUID, consent_id: UUID | None
) -> list[tuple[events_repo.NewEvent, str]]:
    """One or two NewEvents for a harness event, each with the harness ref it stands for."""
    etype, payload, mode = _payload(ev)
    src = _event_source(ev.channel, ev.kind)
    common: dict[str, Any] = {
        "patient_id": patient_id,
        "occurred_at": ev.occurred_at,
        "recorded_at": ev.recorded_at,
        "source": src,
        "reporter_mode": mode,
        "channel": src,
        "consent_id": consent_id,
    }
    out = [
        (
            events_repo.NewEvent(
                type=etype,
                payload=payload,
                idempotency_key=f"{_KEY}:{ev.event_id}",
                event_id=UUID(ev.event_id),
                **common,
            ),
            ev.ref,
        )
    ]
    m = _REASON.match(ev.text) if ev.kind == "checkin" else None
    if m:  # the free text of a check-in (stated reason or reply) is its own note in the real schema
        nid = det_id(_KEY, "note", ev.event_id)
        out.append(
            (
                events_repo.NewEvent(
                    type="ContextNote",
                    payload={"origin": "patient_text", "text_tokenised": m.group(1)},
                    idempotency_key=f"{_KEY}:{nid}",
                    event_id=nid,
                    **{**common, "reporter_mode": "self"},
                ),
                ev.ref,
            )
        )
    return out


def _person_id(token: str) -> UUID:
    return det_id(_KEY, "person", token)


def cleanup(conn: Any = None) -> dict[str, int]:
    """Delete every row this module may have written (eval tokens only). Idempotent."""
    if conn is None:
        from cm.core.db import transaction

        with transaction() as c:
            return cleanup(c)
    tokens = list(TOKEN_OF.values())
    pids = [_person_id(t) for t in tokens]
    conn.execute(
        "SET LOCAL cm.allow_erasure = 'on'"
    )  # the documented bypass of the append-only guard
    n: dict[str, int] = {}
    n["documents"] = conn.execute(
        "DELETE FROM cm.documents WHERE patient_token = ANY(%s)", (tokens,)
    ).rowcount  # text_chunks cascade
    n["events"] = conn.execute(
        "DELETE FROM cm.events WHERE patient_id IN (SELECT patient_id FROM cm.patients "
        "WHERE person_id = ANY(%s))",
        (pids,),
    ).rowcount
    n["consents"] = conn.execute(
        "DELETE FROM cm.consents WHERE person_id = ANY(%s)", (pids,)
    ).rowcount
    n["patients"] = conn.execute(
        "DELETE FROM cm.patients WHERE person_id = ANY(%s)", (pids,)
    ).rowcount
    n["persons"] = conn.execute(
        "DELETE FROM cm.persons WHERE person_id = ANY(%s)", (pids,)
    ).rowcount
    return n


def leftovers(conn: Any = None) -> dict[str, int]:
    """Row counts still present for the eval tokens (all zero after ``cleanup``)."""
    if conn is None:
        from cm.core.db import transaction

        with transaction() as c:
            return leftovers(c)
    tokens, pids = list(TOKEN_OF.values()), [_person_id(t) for t in TOKEN_OF.values()]
    q = {
        "documents": (
            "SELECT count(*) AS n FROM cm.documents WHERE patient_token = ANY(%s)",
            tokens,
        ),
        "chunks": (
            "SELECT count(*) AS n FROM cm.text_chunks WHERE patient_token = ANY(%s)",
            tokens,
        ),
        "events": (
            "SELECT count(*) AS n FROM cm.events WHERE patient_id IN "
            "(SELECT patient_id FROM cm.patients WHERE person_id = ANY(%s))",
            pids,
        ),
        "consents": ("SELECT count(*) AS n FROM cm.consents WHERE person_id = ANY(%s)", pids),
        "patients": ("SELECT count(*) AS n FROM cm.patients WHERE person_id = ANY(%s)", pids),
        "persons": ("SELECT count(*) AS n FROM cm.persons WHERE token = ANY(%s)", tokens),
    }
    return {k: int(conn.execute(sql, (arg,)).fetchone()["n"]) for k, (sql, arg) in q.items()}


@dataclass
class DbIndex:
    """What the harness needs from an index (``patient``, ``as_of``, ``chunks``, ``build_ms``), DB flavoured."""

    patient: str
    as_of: datetime
    cfg: dict[str, Any]
    chunks: list[Any]
    build_ms: float
    stats: Any = None
    cache: dict[str, Any] = field(default_factory=dict)
    key: tuple[Any, ...] = ()
    rollups: bool = True
    n_rows: int = 0  # text_chunks rows for the eval patients right after the build (loss detector)


@dataclass
class Session:
    """One load of the harness log into caremem_test. ``close()`` (or the context manager) removes it."""

    log: Any
    alias: dict[str, str] = field(default_factory=dict)  # event uuid (str) -> harness ref
    n_events: int = 0
    n_companions: int = 0
    active: tuple[Any, ...] | None = None
    closed: bool = False
    reloads: int = 0

    # ---------------------------------------------------------------- load
    def load(self) -> Session:
        require_test_db()
        from cm.core.db import transaction

        with transaction() as conn:
            cleanup(conn)  # a crashed earlier run leaves deterministic rows; start clean
            for token in TOKEN_OF.values():
                if conn.execute("SELECT 1 FROM cm.persons WHERE token=%s", (token,)).fetchone():
                    raise DbBackendRefused(
                        f"token {token} is taken by a row this harness did not write"
                    )
            clinic = conn.execute(
                "SELECT clinic_id FROM cm.clinics ORDER BY clinic_id LIMIT 1"
            ).fetchone()
            if not clinic:
                raise DbBackendRefused("caremem_test has no clinic: run the seed first")
            from cm.sim.gen import DAY0

            for role, code in (("main", self.log.patient), ("foreign", self.log.foreign)):
                token = TOKEN_OF[role]
                pid, cid = self._patient(conn, token, clinic["clinic_id"], DAY0)
                batch = []
                for e in self.log.of(code):
                    for ne, ref in to_new_events(e, pid, cid):
                        batch.append(ne)
                        self.alias[str(ne.event_id)] = ref
                    self.n_events += 1
                events_repo.bulk_append(batch, conn=conn)
                self.n_companions += len(batch) - len(self.log.of(code))
        return self

    @staticmethod
    def _patient(conn: Any, token: str, clinic_id: UUID, day0: Any) -> tuple[UUID, UUID]:
        person = _person_id(token)
        conn.execute(
            "INSERT INTO cm.persons (person_id, role, token, clinic_id) VALUES (%s,'patient',%s,%s)",
            (person, token, clinic_id),
        )
        pid = det_id(_KEY, "patient", token)
        conn.execute(
            "INSERT INTO cm.patients (patient_id, person_id, clinic_id, treatment_start, regimen) "
            "VALUES (%s,%s,%s,%s,'eval-regimen')",
            (pid, person, clinic_id, day0),
        )
        cid = consent_repo.record_consent(
            person,
            "telegram",
            "daily_checkin",
            "granted",
            datetime(2000, 1, 1, tzinfo=day0_tz()),
            "console",
            conn=conn,
        )
        return pid, cid

    def present(self) -> bool:
        """True while both eval patients and all their events are still in the database."""
        from cm.core.db import transaction

        with transaction() as conn:
            n = conn.execute(
                "SELECT count(*) AS n FROM cm.events e JOIN cm.patients p USING (patient_id) "
                "WHERE p.person_id = ANY(%s)",
                ([_person_id(t) for t in TOKEN_OF.values()],),
            ).fetchone()["n"]
        return int(n) == len(self.alias)

    def ensure(self) -> bool:
        """Re-load if the rows vanished (the shared test database is re-seeded by pytest runs). True if reloaded."""
        require_test_db()
        if self.present():
            return False
        self.alias.clear()
        self.n_events = self.n_companions = 0
        self.load()
        self.reloads += 1
        return True

    # ---------------------------------------------------------------- index + search
    def token(self) -> str:
        return TOKEN_OF["main"]

    def _count(self, conn: Any = None) -> int:
        if conn is None:
            from cm.core.db import transaction

            with transaction() as c:
                return self._count(c)
        return int(
            conn.execute(
                "SELECT count(*) AS n FROM cm.text_chunks WHERE patient_token = ANY(%s)",
                (list(TOKEN_OF.values()),),
            ).fetchone()["n"]
        )

    def build(
        self,
        as_of: datetime,
        cfg: dict[str, Any],
        embedder: Any,
        key: tuple[Any, ...],
        rollups: bool = True,
    ) -> DbIndex:
        """Fresh index for one (as_of, strategy, size, overlap): wipe the eval patient's index, build, read back."""
        from cm.core.db import transaction
        from cm.rag.index import build_patient_index

        require_test_db()
        t0 = time.perf_counter()
        with transaction() as conn:
            conn.execute(
                "DELETE FROM cm.documents WHERE patient_token = ANY(%s)", (list(TOKEN_OF.values()),)
            )
            stats = build_patient_index(
                self.token(),
                as_of,
                strategy=cfg["strategy"],
                size=cfg["size"],
                overlap=cfg["overlap"],
                embedder=embedder,
                rollups=rollups,
                conn=conn,
            )
            rows = search_repo.fetch_pool(
                search_repo.SearchFilter(self.token(), as_of, _ALL), conn=conn
            )
            n_rows = self._count(conn)
        self.active = key
        chunks = [
            self.to_chunk(r) for r in rows if (r["extra"] or {}).get("role", "chunk") == "chunk"
        ]
        return DbIndex(
            self.log.patient,
            as_of,
            dict(cfg),
            chunks,
            round((time.perf_counter() - t0) * 1000, 2),
            stats,
            key=key,
            rollups=rollups,
            n_rows=n_rows,
        )

    def retry(self, fn: Any) -> Any:
        """Run ``fn``; if the shared database was re-seeded or deadlocked under us, reload and try again."""
        last: BaseException | None = None
        for attempt in range(8):
            try:
                return fn()
            except _transient() as e:
                last = e
                time.sleep(0.5 * (attempt + 1))
                self.ensure()
        raise RuntimeError(f"db backend gave up after repeated interference: {type(last).__name__}")

    def build_retry(
        self,
        as_of: datetime,
        cfg: dict[str, Any],
        embedder: Any,
        key: tuple[Any, ...],
        rollups: bool = True,
    ) -> DbIndex:
        return self.retry(lambda: self.build(as_of, cfg, embedder, key, rollups))

    def search_retry(
        self, idx: DbIndex, plan: Any, cfg: dict[str, Any], embedder: Any, query: str
    ) -> tuple[list[Any], float, list[str], bool]:
        """Search; when the index vanished or changed mid-search, rebuild it in place and search again."""
        state = {"first": True}

        def once() -> tuple[list[Any], float, list[str], bool]:
            if not state["first"]:
                fresh = self.build(idx.as_of, idx.cfg, embedder, idx.key, idx.rollups)
                idx.chunks, idx.n_rows = fresh.chunks, fresh.n_rows
            state["first"] = False
            out = self.search(plan, cfg, idx.as_of, embedder, query)
            if self._count() != idx.n_rows:
                raise IndexLost("index rows changed during the search")
            return out

        return self.retry(once)

    def sources(self, extra: dict[str, Any]) -> tuple[str, ...]:
        """Harness refs behind a DB chunk (``extra.source_event_ids``, rollups list a whole window)."""
        ids = extra.get("source_event_ids") or []
        return tuple(dict.fromkeys(self.alias.get(str(i), f"?{str(i)[:8]}") for i in ids))

    def to_chunk(self, r: dict[str, Any]) -> Any:
        from cm.eval.rag_eval import Chunk, est_tokens
        from cm.rag.retrieve import ref_of

        extra = r.get("extra") or {}
        src = self.sources(extra)
        foreign = any(s.startswith("?") or self._foreign(s) for s in src)
        return Chunk(
            ref_of(r["chunk_id"]),
            r["content"],
            self.log.foreign if foreign else self.log.patient,
            str(extra.get("kind", "event")),
            src,
            r["occurred_at"] or r["recorded_at"],
            r["recorded_at"],
            est_tokens(r["content"]),
        )

    def _foreign(self, ref: str) -> bool:
        ev = self.log.by_ref().get(ref)
        return bool(ev and ev.patient != self.log.patient)

    def search(
        self, plan: Any, cfg: dict[str, Any], as_of: datetime, embedder: Any, query: str
    ) -> tuple[list[Any], float, list[str], bool]:
        """Real ``search_patient_memory``; returns (harness Hits, ms, notes, db_abstain)."""
        from datetime import timedelta

        from cm.eval.rag_eval import FakeRerankModel, Hit
        from cm.rag import rerank as rerank_mod
        from cm.rag.retrieve import search_patient_memory

        require_test_db()
        kw: dict[str, Any] = {"recency": bool(plan.recent)}
        if plan.last_week:
            kw["date_from"] = as_of - timedelta(days=7)
        patch = (
            mock.patch.object(rerank_mod, "_worker", lambda: FakeRerankModel(plan.need))
            if cfg["rerank"] == "llm"
            else contextlib.nullcontext()
        )
        with patch:  # offline stand-in for the WORKER reranker; no LLM call is possible
            res = search_patient_memory(
                self.token(),
                query,
                as_of,
                top_k=cfg["top_k"],
                mode=cfg["mode"],
                rerank=cfg["rerank"],
                embedder=embedder,
                **kw,
            )
        hits = [
            Hit(
                self.to_chunk(
                    {
                        "chunk_id": h.chunk_id,
                        "content": h.text,
                        "extra": h.extra,
                        "occurred_at": h.occurred_at,
                        "recorded_at": h.recorded_at,
                    }
                ),
                h.score,
            )
            for h in res.hits
        ]
        return hits, float(res.timings_ms.get("total_ms", 0.0)), list(res.notes), bool(res.abstain)

    # ---------------------------------------------------------------- close
    def close(self) -> dict[str, int]:
        if self.closed:
            return {}
        self.closed = True
        return cleanup()

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


_ALL = ("normal", "hiv_adjacent", "mental_health")


def day0_tz() -> Any:
    from cm.core.clock import IST

    return IST


@contextlib.contextmanager
def loaded(log: Any) -> Iterator[Session]:
    s = Session(log).load()
    try:
        yield s
    finally:
        s.close()
