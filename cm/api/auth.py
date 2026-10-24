"""Lane G: passwords (hashlib.scrypt) and HS256 session tokens (INTEGRATION_DECISIONS a5 P4)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import uuid
from typing import Any

import jwt

from cm.core.config import load_settings

_N, _R, _P = 2**14, 8, 1
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """scrypt$n$r$p$salt$hash (urlsafe base64)."""
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    b = base64.urlsafe_b64encode
    return f"scrypt${_N}${_R}${_P}${b(salt).decode()}${b(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, want = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode(),
            salt=base64.urlsafe_b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return hmac.compare_digest(dk, base64.urlsafe_b64decode(want))
    except (ValueError, TypeError):
        return False


def _key() -> str:
    key = load_settings().jwt_signing_key
    if not key:
        raise RuntimeError("JWT_SIGNING_KEY is not set (put it in .env)")
    return key


def create_access_token(claims: dict[str, Any]) -> str:
    """Sign claims {sub, role, person_id, clinic_id, district_id, tv} adding iat, exp, jti."""
    now = int(time.time())
    body = {
        **claims,
        "iat": now,
        "exp": now + load_settings().jwt_ttl_min * 60,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(body, _key(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify signature and expiry; raises jwt.PyJWTError on any failure."""
    return jwt.decode(token, _key(), algorithms=[ALGORITHM])
