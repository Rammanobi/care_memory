"""Lane B: approved message templates (read-only list in slice 1)."""
# ruff: noqa: S608  (SQL is assembled from fixed fragments; every value is a bound parameter)
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

from fastapi import APIRouter, Depends

from cm.api.deps import User, require_roles
from cm.contracts.review import Template
from cm.core.db import transaction

router = APIRouter(tags=["templates"])


@router.get("/templates", response_model=list[Template])
def list_templates(
    status: str | None = None,
    key: str | None = None,
    lang: str | None = None,
    _: User = Depends(require_roles("doctor", "admin")),
) -> list[Template]:
    where, args = ["true"], []
    for col, val in (("t.status", status), ("t.key", key), ("t.lang", lang)):
        if val:
            where.append(f"{col} = %s")
            args.append(val)
    with transaction() as conn:
        rows = conn.execute(
            "SELECT t.*, p.token AS approved_by_token FROM cm.templates t "
            "LEFT JOIN cm.persons p ON p.person_id = t.approved_by WHERE "
            + " AND ".join(where)
            + " ORDER BY t.key",
            args,
        ).fetchall()
    return [
        Template(
            template_id=r["template_id"],
            key=r["key"],
            lang=r["lang"],
            body=r["body"],
            slots=r["slots"],
            tier=r["tier"],
            status=r["status"],
            approved_by=r["approved_by_token"],
            approved_at=r["approved_at"],
        )
        for r in rows
    ]
