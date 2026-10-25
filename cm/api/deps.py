"""Lane G: shared FastAPI dependencies, error type and Problem rendering."""
# ruff: noqa: S608  (SQL is assembled from fixed fragments; every value is a bound parameter)
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from cm.api import auth, firebase_auth
from cm.contracts.api import Problem
from cm.core import clock
from cm.core.db import transaction

COOKIE = "cm_session"


class ApiError(Exception):
    """Raised by routes; rendered as an api.Problem body."""

    def __init__(
        self, status: int, title: str, code: str | None = None, detail: str | None = None
    ) -> None:
        super().__init__(title)
        self.status, self.title, self.code, self.detail = status, title, code, detail


def problem_response(
    status: int, title: str, code: str | None = None, detail: str | None = None
) -> JSONResponse:
    body = Problem(title=title, detail=detail, status=status, code=code)
    return JSONResponse(status_code=status, content=body.model_dump(exclude_none=True))


@dataclass(frozen=True)
class User:
    person_id: UUID
    role: str
    token: str
    username: str | None
    display_name: str | None
    clinic_id: UUID | None
    district_id: UUID | None


def _credentials(request: Request) -> tuple[str, bool]:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip(), False
    cookie = request.cookies.get(COOKIE)
    if cookie:
        return cookie, True
    raise ApiError(401, "Not signed in", "unauthenticated")


def display_name_of(conn: Any, person_id: UUID) -> str | None:
    row = conn.execute(
        "SELECT enc_name FROM cm.identity_vault WHERE person_id=%s", (person_id,)
    ).fetchone()
    return bytes(row["enc_name"]).decode() if row and row["enc_name"] else None


def _firebase_user(token: str) -> User:
    """AUTH_MODE=firebase: verify the ID token, then cross-check claims role/pid/tv against the DB."""
    try:
        claims = firebase_auth.verify(token)
    except firebase_auth.FirebaseAuthError as exc:
        raise ApiError(401, "Session expired or invalid", "unauthenticated") from exc
    role, pid, tv = claims.get("role"), claims.get("pid"), claims.get("tv")
    person_id = parse_uuid(pid) if isinstance(pid, str) else None
    if not isinstance(role, str) or person_id is None or not isinstance(tv, int):
        raise ApiError(403, "No role assigned to this account", "no_role")
    with transaction() as conn:
        row = conn.execute(
            "SELECT c.token_version, c.active, c.username, p.token, p.role, p.clinic_id, p.district_id "
            "FROM cm.auth_credentials c JOIN cm.persons p USING (person_id) WHERE c.person_id=%s",
            (str(person_id),),
        ).fetchone()
        if not row or not row["active"] or row["role"] != role or row["token_version"] != tv:
            raise ApiError(401, "Session no longer valid", "unauthenticated")
        name = display_name_of(conn, person_id)
    return User(person_id, row["role"], row["token"], row["username"], name, row["clinic_id"],
                row["district_id"])


def current_user(request: Request) -> User:
    """Validate the session token and its token_version against auth_credentials.

    AUTH_MODE=firebase: an ``Authorization: Bearer`` token is a Firebase ID token; the ``cm_session``
    cookie, if present, is still checked by the unchanged local path below.
    """
    token, via_cookie = _credentials(request)
    if not via_cookie and firebase_auth.mode() == "firebase":
        return _firebase_user(token)
    if (
        via_cookie
        and request.method not in ("GET", "HEAD", "OPTIONS")
        and request.headers.get("x-cm-client") != "web"
    ):
        raise ApiError(403, "Missing X-CM-Client header", "csrf")
    try:
        claims = auth.decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise ApiError(401, "Session expired or invalid", "unauthenticated") from exc
    with transaction() as conn:
        row = conn.execute(
            "SELECT c.token_version, c.active, c.username, p.token, p.role, p.clinic_id, p.district_id "
            "FROM cm.auth_credentials c JOIN cm.persons p USING (person_id) WHERE c.person_id=%s",
            (claims["person_id"],),
        ).fetchone()
        if not row or not row["active"] or row["token_version"] != claims.get("tv"):
            raise ApiError(401, "Session no longer valid", "unauthenticated")
        name = display_name_of(conn, UUID(claims["person_id"]))
    return User(
        UUID(claims["person_id"]),
        row["role"],
        row["token"],
        row["username"],
        name,
        row["clinic_id"],
        row["district_id"],
    )


def require_roles(*roles: str) -> Callable[..., User]:
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise ApiError(403, "Not allowed for this role", "forbidden_scope")
        return user

    return dep


def now() -> Any:
    return clock.now()


def parse_uuid(value: str) -> UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def parse_cursor(cursor: str | None) -> int:
    """Page offset from a cursor string: ASCII digits only, clamped so a huge value cannot overflow SQL."""
    return min(int(cursor), 1_000_000_000) if cursor and cursor.isascii() and cursor.isdigit() else 0


def display_code(token: str) -> str:
    """Person token P-0142 -> display code PT-0142 (the UI's patient code)."""
    return "PT-" + token.split("-", 1)[1] if token.startswith("P-") else token


def token_from_code(code: str) -> str:
    return "P-" + code.split("-", 1)[1] if code.upper().startswith("PT-") else code


def resolve_patient(conn: Any, key: str) -> dict[str, Any]:
    """Find a patient by uuid, person token (P-0142) or display code (PT-0142)."""
    uid = parse_uuid(key)
    sql = (
        "SELECT p.*, per.token, per.person_id AS pid FROM cm.patients p JOIN cm.persons per USING (person_id) "
        + ("WHERE p.patient_id=%s" if uid else "WHERE per.token=%s")
    )
    row = conn.execute(sql, (uid if uid else token_from_code(key.upper()),)).fetchone()
    if not row:
        raise ApiError(404, "Patient not found", "not_found")
    return row
