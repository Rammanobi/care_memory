"""Lane B: consent state read (doctor console). Patient consent switches live under /portal/consents."""
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from cm.api.deps import ApiError, User, now, require_roles
from cm.contracts.admin import ConsentState
from cm.core.db import transaction
from cm.store import consent as consent_repo

router = APIRouter(tags=["consent"])


@router.get("/consents/{person_id}", response_model=ConsentState)
def get_consent(
    person_id: UUID, _: User = Depends(require_roles("doctor", "admin"))
) -> ConsentState:
    at = now()
    with transaction() as conn:
        if not conn.execute("SELECT 1 FROM cm.persons WHERE person_id=%s", (person_id,)).fetchone():
            raise ApiError(404, "Person not found", "not_found")
        state = consent_repo.consent_state(person_id, at, conn=conn)
        return ConsentState(person_id=person_id, by_source_purpose=state, ledger=[])
