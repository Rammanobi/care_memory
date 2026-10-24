"""Lane B: dashboard tiles, clinics and the clinic summary (contract dashboard.ClinicSummary)."""
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

from statistics import median
from typing import Any

from fastapi import APIRouter, Depends

from cm.api import readmodels as rm
from cm.api.deps import ApiError, User, now, parse_uuid, require_roles
from cm.api.portal_models import (
    CLINIC_AREA,
    ClinicOut,
    DistrictClinic,
    DistrictOut,
    DistrictQuiet,
    TilesOut,
)
from cm.api.suppress import SMALL_CELL_THRESHOLD
from cm.contracts.dashboard import ClinicSummary
from cm.core import clock
from cm.core.db import transaction

router = APIRouter(tags=["dashboard"])
console = require_roles("doctor", "admin")


def _clinics(conn: Any) -> list[dict[str, Any]]:
    return conn.execute("SELECT clinic_id, name FROM cm.clinics ORDER BY name").fetchall()


@router.get("/clinics", response_model=list[ClinicOut])
def list_clinics(_: User = Depends(console)) -> list[ClinicOut]:
    with transaction() as conn:
        rows = _clinics(conn)
    return [
        ClinicOut(
            clinic_id=r["clinic_id"],
            id=rm.clinic_slug(r["name"]),
            name=r["name"],
            area=CLINIC_AREA.get(rm.clinic_slug(r["name"]), ""),
        )
        for r in rows
    ]


@router.get("/dashboard/tiles", response_model=TilesOut)
def tiles(clinic: str | None = None, _: User = Depends(console)) -> TilesOut:
    at = now()
    with transaction() as conn:
        pts = rm.ui_patients(conn, at)
        pend = conn.execute(
            "SELECT count(*) FILTER (WHERE COALESCE(payload->>'subkind','') = 'patient_request') AS rq, "
            "count(*) FILTER (WHERE COALESCE(payload->>'subkind','') <> 'patient_request') AS ap "
            "FROM cm.approvals WHERE status='pending' AND created_at <= %s",
            (at,),
        ).fetchone()
        sim_day = clock.current_sim_day(conn)
    if clinic:
        pts = [p for p in pts if p.clinic == clinic.lower()]
    return TilesOut(
        all=len(pts),
        needs=sum(p.needs_me for p in pts),
        requests=sum(p.has_request for p in pts),
        quiet=sum(p.quiet for p in pts),
        visit=sum(p.visit_this_week for p in pts),
        red=sum(p.level == "red" for p in pts),
        track=sum(p.level == "grn" for p in pts),
        pending_requests=pend["rq"],
        pending_approvals=pend["ap"],
        sim_day=sim_day,
        as_of=at,
    )


def _clinic_id(conn: Any, key: str) -> Any:
    uid = parse_uuid(key)
    for r in _clinics(conn):
        if r["clinic_id"] == uid or rm.clinic_slug(r["name"]) == key.lower():
            return r["clinic_id"], rm.clinic_slug(r["name"])
    raise ApiError(404, "Clinic not found", "not_found")


@router.get("/dashboard/clinic/{clinic_id}/summary", response_model=ClinicSummary)
def clinic_summary(clinic_id: str, _: User = Depends(console)) -> ClinicSummary:
    at = now()
    with transaction() as conn:
        cid, slug = _clinic_id(conn, clinic_id)
        pts = [p for p in rm.ui_patients(conn, at) if p.clinic == slug]
        ids = [p.patient_id for p in pts]
        rows = conn.execute(
            "SELECT a.tier, a.status, a.due_at, d.decided_at, a.created_at FROM cm.approvals a "
            "LEFT JOIN cm.review_decisions d USING (approval_id) "
            "WHERE a.patient_id = ANY(%s) AND a.created_at <= %s",
            (ids, at),
        ).fetchall()
    by_tier = {"red": 0, "amber": 0, "green": 0}
    for p in pts:
        by_tier[{"red": "red", "amb": "amber", "grn": "green"}[p.base]] += 1
    open_rev = {"red": 0, "amber": 0, "green": 0}
    mins: dict[str, list[float]] = {"red": [], "amber": [], "green": []}
    decided = accepted = overdue = 0
    for r in rows:
        if r["status"] == "pending":
            open_rev[r["tier"]] += 1
            overdue += r["due_at"] < at
        elif r["decided_at"]:
            decided += 1
            accepted += r["status"] in ("approved", "edited")
            mins[r["tier"]].append((r["decided_at"] - r["created_at"]).total_seconds() / 60)
    return ClinicSummary(
        clinic_id=cid,
        as_of=rm.sim_date(at),
        patients_by_tier=by_tier,
        open_reviews=open_rev,
        sla={t: (round(median(v), 1) if v else None) for t, v in mins.items()},
        overdue_reviews=overdue,
        visits_due=sum(p.visit_this_week for p in pts),
        acceptance_rate=round(accepted / decided, 3) if decided else None,
    )


def _hide(n: int, name: str, hidden: list[str]) -> int | None:
    if 1 <= n < SMALL_CELL_THRESHOLD:
        hidden.append(name)
        return None
    return n


@router.get("/dashboard/district", response_model=DistrictOut)
def district(clinic: str | None = None, _: User = Depends(console)) -> DistrictOut:
    """District page data. Counts of 1..SMALL_CELL_THRESHOLD-1 are returned as null and listed in `suppressed`."""
    at = now()
    with transaction() as conn:
        pts = rm.ui_patients(conn, at)
        clinics = _clinics(conn)
        pend = conn.execute(
            "SELECT patient_id, count(*) AS n FROM cm.approvals WHERE status='pending' "
            "AND created_at <= %s AND patient_id IS NOT NULL AND COALESCE(payload->'data'->>'archived','false') <> 'true' "
            "GROUP BY patient_id",
            (at,),
        ).fetchall()
    by_patient = {r["patient_id"]: r["n"] for r in pend}

    def pct(p: Any) -> int:
        return round((20 - len(p.missed) - p.no_data) / 20 * 100)

    rows: list[DistrictClinic] = []
    for c in clinics:
        slug = rm.clinic_slug(c["name"])
        if clinic and slug != clinic.lower():
            continue
        ps = [p for p in pts if p.clinic == slug]
        hidden: list[str] = []
        rows.append(
            DistrictClinic(
                id=slug,
                name=c["name"],
                area=CLINIC_AREA.get(slug, ""),
                patients=_hide(len(ps), "patients", hidden),
                adherence=round(sum(pct(p) for p in ps) / len(ps)) if ps else None,
                quiet=_hide(sum(p.quiet for p in ps), "quiet", hidden),
                pending=_hide(sum(by_patient.get(p.patient_id, 0) for p in ps), "pending", hidden),
                suppressed=hidden,
            )
        )
    shown = {r.id for r in rows}
    quiet = [
        DistrictQuiet(code=p.code, clinic=p.clinic, why=p.why, adherence=pct(p), no_data=p.no_data)
        for p in pts
        if p.quiet and p.clinic in shown
    ]
    hid: list[str] = []
    return DistrictOut(
        as_of=at,
        small_cell_threshold=SMALL_CELL_THRESHOLD,
        clinics=rows,
        quiet_patients=quiet,
        total_patients=_hide(sum(1 for p in pts if p.clinic in shown), "total", hid),
        total_pending_approvals=sum(
            by_patient.get(p.patient_id, 0) for p in pts if p.clinic in shown
        ),
    )
