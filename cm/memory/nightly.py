"""Lane C: nightly memory run over all patients (feature_specs/04 F4, cm-nightly job)."""

from __future__ import annotations

from datetime import datetime

from cm.core import clock
from cm.core.db import transaction
from cm.memory.pipeline import run_patient
from cm.store import ai_repo, memory_repo


def run_nightly(as_of: datetime | None = None) -> dict[str, int]:
    """Memory pipeline for every patient at one instant. Idempotent; the narrator step stays in cm.jobs.nightly."""
    at = as_of or clock.now()
    with transaction() as conn:
        day0, _ = ai_repo.sim_day0(conn=conn)
        pids = memory_repo.list_patient_ids(conn=conn)
    done = skipped = 0
    for pid in pids:
        if run_patient(pid, at, day0=day0) is None:
            skipped += 1
        else:
            done += 1
    return {"patients": len(pids), "computed": done, "skipped": skipped}
