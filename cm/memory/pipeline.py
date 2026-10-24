"""Lane C: the nightly memory pipeline for one patient (1.4).

``compute_memory`` is pure (events + prior belief history in, numbers out). ``run_patient`` is the only impure
part: it reads through ``cm.store`` repos, calls the pure function, and upserts through ``cm.store.memory_repo``.
Idempotent: the same ``as_of`` twice reads the same past (history is strictly before ``as_of``) and upserts the
same keys, so the rows are identical. No raw SQL here.

Order: features -> weekday beliefs lifecycle -> risk with interval -> R1-R6 reconcile -> engine conflicts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid5

from cm.contracts.admin import RuleThresholds
from cm.contracts.memory import Conflict, FeatureVector, RiskScore
from cm.core import clock
from cm.core.clock import ist_date
from cm.core.db import transaction
from cm.memory.conflicts import EngineConflict, self_report_vs_refill, weekday_pattern_conflict
from cm.memory.detectors.weekday import weekday_effect
from cm.memory.features import WEEKDAYS, PatientFeatures, _checkins, compute_features
from cm.memory.lifecycle import BeliefState, advance_belief_state
from cm.memory.risk import score_risk
from cm.rules import merge_upsert, reconcile_frame
from cm.rules.reconcile import patient_from_events
from cm.store import events_repo, memory_repo, settings_repo

ENGINE_VERSION = "memory_v1"
BELIEF_NS = UUID("9a6e1b34-52c7-5d08-8f3a-c4d7e0b21f65")
ADH_PRIOR = (9.0, 1.0)  # Beta(taken, missed) prior: 10% miss rate before any data
WEEKDAY_WINDOW = 56
RISK_MIN_DAY = 3


@dataclass(frozen=True)
class MemoryResult:
    patient_id: UUID
    as_of: date
    day: int
    features: FeatureVector
    patient_features: PatientFeatures
    beliefs: tuple[dict[str, Any], ...]
    belief_evidence: Mapping[UUID, tuple[UUID, ...]]
    risk: RiskScore | None
    conflicts: tuple[Conflict, ...]  # R1-R6 reconcile output (open and closed known at as_of)
    engine_conflicts: tuple[EngineConflict, ...]


def belief_id_for(pid: UUID | str, subject: str) -> UUID:
    return uuid5(BELIEF_NS, f"{pid}|weekday_miss|{subject}")


def _window(by_day: Mapping[date, dict[str, Any]], today: date, days: int) -> tuple[int, int]:
    taken = missed = 0
    for d, e in by_day.items():
        if 0 <= (today - d).days < days:
            s = e["payload"].get("status")
            taken += s == "taken"
            missed += s == "missed"
    return taken, missed


def _weekday_counts(
    by_day: Mapping[date, dict[str, Any]], today: date
) -> dict[str, tuple[int, int]]:
    tot = [0] * 7
    mis = [0] * 7
    for d, e in by_day.items():
        s = e["payload"].get("status")
        if 0 <= (today - d).days < WEEKDAY_WINDOW and s in ("taken", "missed"):
            tot[d.weekday()] += 1
            mis[d.weekday()] += s == "missed"
    return {WEEKDAYS[k]: (mis[k], tot[k]) for k in range(7)}


def prior_from_history(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Collapse stored rows (ascending ``as_of``) of one belief into the lifecycle's starting state."""
    last = rows[-1]
    support = [r["as_of"] for r in rows if r["posterior"] >= 0.60]
    low_since: date | None = None
    for r in reversed(rows):
        if r["posterior"] < 0.30:
            low_since = r["as_of"]
        else:
            break
    return {
        "state": last["state"],
        "first_seen": rows[0]["first_seen"],
        "last_support": support[-1] if support else rows[0]["first_seen"],
        "low_since": low_since,
        "confirmed_at": last["confirmed_at"],
    }


def _advance_weekday_beliefs(
    pid: UUID,
    today: date,
    counts: Mapping[str, tuple[int, int]],
    prior: Mapping[UUID, Mapping[str, Any]],
    by_day: Mapping[date, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[UUID, tuple[UUID, ...]]]:
    rows: list[dict[str, Any]] = []
    evidence: dict[UUID, tuple[UUID, ...]] = {}
    for k, wd in enumerate(WEEKDAYS):
        m, n = counts[wd]
        b = weekday_effect(
            str(pid),
            wd,
            today,
            m,
            n,
            sum(v[0] for w, v in counts.items() if w != wd),
            sum(v[1] for w, v in counts.items() if w != wd),
        )
        bid = belief_id_for(pid, wd[:3].lower())
        pr = prior.get(bid)
        if (pr is None and b.state is None) or (pr and pr["state"] == "retired"):
            continue
        o = today.toordinal()
        st = (
            BeliefState(
                pr["state"],
                pr["first_seen"].toordinal(),
                pr["last_support"].toordinal(),
                pr["low_since"].toordinal() if pr["low_since"] else None,
            )
            if pr
            else BeliefState("hypothesis", o, o)
        )
        st = advance_belief_state(
            st,
            o,
            b.posterior,
            confirm_met=b.state == "confirmed",
            supported_today=b.state is not None,
        )
        confirmed_at = pr["confirmed_at"] if pr else None
        if st.state == "confirmed" and confirmed_at is None:
            confirmed_at = today
        rows.append(
            {
                "belief_id": bid,
                "as_of": today,
                "patient_id": pid,
                "kind": "weekday_miss",
                "subject": wd[:3].lower(),
                "state": st.state,
                "posterior": b.posterior,
                "ci_low": b.ci_low,
                "ci_high": b.ci_high,
                "n_instances": m,
                "first_seen": date.fromordinal(st.first_day),
                "confirmed_at": confirmed_at,
                "retired_at": today if st.state == "retired" else None,
                "retired_reason": st.retired_reason,
            }
        )
        evidence[bid] = tuple(
            e["event_id"]
            for d, e in sorted(by_day.items())
            if d.weekday() == k
            and e["payload"].get("status") == "missed"
            and 0 <= (today - d).days < WEEKDAY_WINDOW
        )
    return rows, evidence


def _feature_vector(
    pid: UUID,
    today: date,
    day: int,
    by_day: Mapping[date, dict[str, Any]],
    counts: Mapping[str, tuple[int, int]],
    pf: PatientFeatures,
) -> FeatureVector:
    def adh(days: int) -> float | None:
        t, m = _window(by_day, today, days)
        return t / (t + m) if t + m else None

    t28, m28 = _window(by_day, today, 28)
    return FeatureVector(
        patient_id=pid,
        as_of=today,
        day=max(0, day),
        engine_version=ENGINE_VERSION,
        adh_7=adh(7),
        adh_14=adh(14),
        adh_28=adh(28),
        adh_alpha=ADH_PRIOR[0] + t28,
        adh_beta=ADH_PRIOR[1] + m28,
        weekday_miss={wd[:3].lower(): v for wd, v in counts.items()},
        refill_gap_days_28=pf.refill_gap_days,
        consecutive_unanswered=min(pf.quiet_days, 14),
    )


def compute_memory(
    pid: UUID,
    events: Sequence[dict[str, Any]],
    as_of: datetime,
    prior: Mapping[UUID, Mapping[str, Any]],
    *,
    day0: date | None = None,
    treatment_start: date | None = None,
    thresholds: RuleThresholds | None = None,
) -> MemoryResult:
    """Pure. ``prior`` maps belief_id to ``prior_from_history`` output; future events are filtered out here."""
    evs = [e for e in events if e["occurred_at"] <= as_of and e["recorded_at"] <= as_of]
    today = ist_date(as_of)
    pf = compute_features(evs, as_of, day0)
    by_day = _checkins(evs)
    counts = _weekday_counts(by_day, today)
    beliefs, evidence = _advance_weekday_beliefs(pid, today, counts, prior, by_day)
    start = treatment_start or (patient_from_events(pid, evs)["treatment_start"] if evs else today)
    day = (today - start).days
    fv = _feature_vector(pid, today, day, by_day, counts, pf)
    short = {w[:3].lower(): w for w in WEEKDAYS}
    active = [short[b["subject"]] for b in beliefs if b["state"] in ("hypothesis", "confirmed")]
    risk = None
    if day >= RISK_MIN_DAY:
        r = score_risk(
            str(pid),
            today,
            adh_alpha=fv.adh_alpha or ADH_PRIOR[0],
            adh_beta=fv.adh_beta or ADH_PRIOR[1],
            refill_gap_days=pf.refill_gap_days,
            consecutive_unanswered=fv.consecutive_unanswered,
            weekday_flag=bool(active),
        )
        risk = RiskScore(
            patient_id=pid,
            as_of=today,
            day=day,
            p=r.p,
            ci_low=r.ci_low,
            ci_high=r.ci_high,
            drivers=[{"feature": k, "contribution": v} for k, v in r.drivers],
            model_version=r.model_version,
        )
    conflicts = (
        reconcile_frame(evs, {"patient_id": pid, "treatment_start": start}, today, thresholds)
        if evs
        else []
    )
    eng = [c for c in [self_report_vs_refill(pid, as_of, evs)] if c]
    eng += weekday_pattern_conflict(pid, as_of, evs, active)
    return MemoryResult(
        pid, today, day, fv, pf, tuple(beliefs), evidence, risk, tuple(conflicts), tuple(eng)
    )


# --------------------------------------------------------------------------- impure edge
def _load_prior(pid: UUID, today: date, conn: Any) -> dict[UUID, dict[str, Any]]:
    return {
        bid: prior_from_history(rows)
        for bid, rows in memory_repo.belief_history(pid, today, conn=conn).items()
    }


def _thresholds() -> RuleThresholds:
    row = settings_repo.get_setting("thresholds")
    return RuleThresholds.model_validate(row["value"]) if row else RuleThresholds()


def _conflict_row(c: Conflict) -> dict[str, Any]:
    return {
        "conflict_id": c.conflict_id,
        "patient_id": c.patient_id,
        "rule": c.rule,
        "tier": c.tier,
        "title": c.title,
        "evidence_ids": list(c.evidence_ids),
        "opened_as_of": c.opened_as_of,
        "closed_as_of": c.closed_as_of,
    }


def _persist(res: MemoryResult, as_of: datetime, conn: Any) -> None:
    pid, today, now = res.patient_id, res.as_of, clock.now()
    feats = res.features.model_dump(mode="json")
    memory_repo.upsert_features(pid, today, feats, ENGINE_VERSION, now, conn=conn)
    for row in res.beliefs:
        memory_repo.upsert_belief(row, conn=conn)
        memory_repo.add_belief_evidence(
            row["belief_id"], res.belief_evidence.get(row["belief_id"], ()), conn=conn
        )
    if res.risk:
        memory_repo.upsert_risk(pid, today, res.risk.model_dump(mode="json"), now, conn=conn)
    stored = [
        Conflict.model_validate({**r, "evidence_ids": list(r["evidence_ids"])})
        for r in memory_repo.stored_conflicts(pid, conn=conn)
        if r["opened_as_of"] <= today
    ]
    merged = merge_upsert(stored, res.conflicts, today)
    # closures first so the one-open-per-(patient, rule) index is never hit by a replacement
    for c in sorted(
        merged, key=lambda c: (c.closed_as_of is None, c.opened_as_of, c.rule, str(c.conflict_id))
    ):
        memory_repo.upsert_conflict(_conflict_row(c), conn=conn)


def run_patient(
    pid: UUID, as_of: datetime | None = None, *, day0: date | None = None, persist: bool = True
) -> MemoryResult | None:
    """One patient, one ``as_of`` instant (default ``clock.now()``). None when the patient has no events."""
    at = as_of or clock.now()
    events = events_repo.query(pid, at)
    if not events:
        return None
    with transaction() as conn:
        res = compute_memory(
            pid,
            events,
            at,
            _load_prior(pid, ist_date(at), conn),
            day0=day0,
            thresholds=_thresholds(),
        )
        if persist:
            _persist(res, at, conn)
    return res


def run_in_memory(
    events: Any, consents: Any, as_of_days: Sequence[int], *, exclude_sources: Sequence[str] = ()
) -> Any:
    """M1 pure in-memory DataFrame engine run (evaluator). Not part of the nightly path; still open."""
    raise NotImplementedError


__all__ = ["MemoryResult", "compute_memory", "run_patient", "run_in_memory"]
