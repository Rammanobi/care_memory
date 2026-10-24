"""Lane G: POST /auth/login, GET /auth/me, POST /auth/logout (INTEGRATION_DECISIONS a5)."""
# ruff: noqa: B008  (FastAPI Depends() defaults)

from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Request, Response

from cm.api import auth
from cm.api.deps import COOKIE, ApiError, User, current_user, display_name_of, now
from cm.contracts.admin import LoginIn, Me, TokenOut
from cm.core.config import load_settings
from cm.core.db import transaction

router = APIRouter(prefix="/auth", tags=["auth"])
_hits: dict[str, deque[float]] = defaultdict(deque)
# Verified against a dummy hash for unknown usernames so timing does not reveal which exist.
_DUMMY = auth.hash_password("not-a-real-password")


def reset_rate_limits() -> None:
    _hits.clear()


def _limited(key: str, per_min: int) -> bool:
    q = _hits[key]
    t = time.monotonic()
    while q and t - q[0] > 60:
        q.popleft()
    if len(q) >= per_min:
        return True
    q.append(t)
    return False


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, response: Response) -> TokenOut:
    ip = request.client.host if request.client else "?"
    if _limited(f"ip:{ip}", int(os.environ.get("LOGIN_PER_IP_PER_MIN", "10"))) or _limited(
        f"u:{body.username}", int(os.environ.get("LOGIN_PER_USER_PER_MIN", "5"))
    ):
        raise ApiError(429, "Too many sign-in attempts", "rate_limited")
    at = now()
    with transaction() as conn:
        row = conn.execute(
            "SELECT c.person_id, c.password_hash, c.token_version, c.active, p.role, p.token, p.clinic_id, "
            "p.district_id FROM cm.auth_credentials c JOIN cm.persons p USING (person_id) WHERE c.username=%s",
            (body.username,),
        ).fetchone()
        ok = auth.verify_password(body.password, row["password_hash"] if row else _DUMMY)
        if not (row and ok and row["active"]):
            raise ApiError(401, "Wrong username or password", "bad_credentials")
        conn.execute(
            "UPDATE cm.auth_credentials SET last_login_at=%s WHERE person_id=%s",
            (at, row["person_id"]),
        )
        conn.execute(
            "INSERT INTO cm.audit_log (at, actor, role, action) VALUES (%s,%s,%s,'login')",
            (at, row["token"], row["role"]),
        )
    token = auth.create_access_token(
        {
            "sub": body.username,
            "role": row["role"],
            "person_id": str(row["person_id"]),
            "clinic_id": str(row["clinic_id"]) if row["clinic_id"] else None,
            "district_id": str(row["district_id"]) if row["district_id"] else None,
            "tv": row["token_version"],
        }
    )
    s = load_settings()
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=s.cookie_secure,
        max_age=s.jwt_ttl_min * 60,
        path="/",
    )
    return TokenOut(access_token=token, role=row["role"], expires_in=s.jwt_ttl_min * 60)


@router.get("/me", response_model=Me)
def me(user: User = Depends(current_user)) -> Me:
    with transaction() as conn:
        name = display_name_of(conn, user.person_id)
    return Me(
        person_id=user.person_id,
        username=user.username,
        token=user.token,
        display_name=name,
        role=user.role,
        clinic_id=user.clinic_id,
        district_id=user.district_id,  # type: ignore[arg-type]
        demo_mode=load_settings().demo_mode,
    )


@router.post("/logout", status_code=204)
def logout(_: User = Depends(current_user)) -> Response:
    resp = Response(status_code=204)
    resp.delete_cookie(COOKIE, path="/")
    return resp
