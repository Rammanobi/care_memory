"""Lane G: Firebase ID token verification for AUTH_MODE=firebase (FIREBASE_PLAN.md 2.2).

Pure and fail-closed, modelled on ``cm/channels/gmail_oidc.py``: RS256 only, ``kid`` must be in Google's
securetoken key set, ``aud`` = project id, ``iss`` = https://securetoken.google.com/<project>, ``exp`` in
the future, ``iat``/``auth_time`` not in the future, non-empty ``sub``, sign-in provider ``password``.
No network in tests: the key fetcher is injectable, and ``set_verifier`` swaps the whole verifier for a
fake. ``AUTH_MODE`` defaults to ``local``, so nothing here runs unless firebase mode is chosen.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from typing import Any

import jwt

SECURETOKEN_CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
)
KeyFetcher = Callable[[str | None], Any]
Verifier = Callable[[str], dict[str, Any]]


class FirebaseAuthError(Exception):
    """The ID token is not acceptable. ``reason`` is a short code, safe to log."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def mode() -> str:
    """``local`` (default) or ``firebase``. Anything else is treated as local."""
    return "firebase" if os.environ.get("AUTH_MODE", "local").strip().lower() == "firebase" else "local"


def project_id() -> str:
    return os.environ.get("FIREBASE_PROJECT_ID", "").strip()


def check_config() -> None:
    """Startup guard: firebase mode without a project id refuses to start."""
    if mode() == "firebase" and not project_id():
        raise RuntimeError("AUTH_MODE=firebase requires FIREBASE_PROJECT_ID")


def verify_firebase_token(
    token: str,
    project: str,
    key_fetcher: KeyFetcher,
    leeway_s: int = 30,
    now: float | None = None,
) -> dict[str, Any]:
    """Return the verified claims or raise FirebaseAuthError."""
    if not project:
        raise FirebaseAuthError("not_configured")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise FirebaseAuthError("malformed") from exc
    if header.get("alg") != "RS256":
        raise FirebaseAuthError("bad_alg")
    try:
        key = key_fetcher(header.get("kid"))
    except Exception as exc:  # noqa: BLE001
        raise FirebaseAuthError("key_unavailable") from exc
    if key is None:
        raise FirebaseAuthError("unknown_kid")
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=project,
            issuer=f"https://securetoken.google.com/{project}",
            leeway=leeway_s,
            options={
                "require": ["exp", "iat", "iss", "aud", "sub"],
                "verify_exp": False,
                "verify_iat": False,
            },
        )
    except jwt.InvalidAudienceError as exc:
        raise FirebaseAuthError("bad_audience") from exc
    except jwt.InvalidIssuerError as exc:
        raise FirebaseAuthError("bad_issuer") from exc
    except jwt.PyJWTError as exc:
        raise FirebaseAuthError("invalid_signature_or_claims") from exc
    _check_times(claims, leeway_s, time.time() if now is None else now)
    if not str(claims.get("sub", "")).strip():
        raise FirebaseAuthError("empty_sub")
    provider = (claims.get("firebase") or {}).get("sign_in_provider")
    if provider != "password":
        raise FirebaseAuthError("bad_provider")
    return claims


def _check_times(claims: dict[str, Any], leeway_s: int, at: float) -> None:
    try:
        exp, iat = float(claims["exp"]), float(claims["iat"])
        auth_time = float(claims.get("auth_time", iat))
    except (TypeError, ValueError) as exc:
        raise FirebaseAuthError("bad_times") from exc
    if exp + leeway_s < at:
        raise FirebaseAuthError("expired")
    if iat - leeway_s > at or auth_time - leeway_s > at:
        raise FirebaseAuthError("issued_in_future")


def securetoken_cert_fetcher(http_get: Callable[[str], tuple[bytes, str]] | None = None) -> KeyFetcher:
    """Production fetcher: Google's x509 certs by kid, cached per process honouring Cache-Control max-age.

    ``http_get(url) -> (body, cache_control)``; network (httpx) is used only when none is injected.
    """
    cache: dict[str, Any] = {}
    expires = [0.0]

    def fetch(kid: str | None) -> Any:
        if not cache or kid not in cache or time.time() >= expires[0]:
            if http_get is None:
                import httpx

                resp = httpx.get(SECURETOKEN_CERTS_URL, timeout=5.0)
                resp.raise_for_status()
                raw, cc = resp.content, resp.headers.get("cache-control", "")
            else:
                raw, cc = http_get(SECURETOKEN_CERTS_URL)
            from cryptography.x509 import load_pem_x509_certificate

            m = re.search(r"max-age=(\d+)", cc or "")
            cache.clear()
            for k, pem in json.loads(raw).items():
                cache[k] = load_pem_x509_certificate(pem.encode()).public_key()
            expires[0] = time.time() + (int(m.group(1)) if m else 3600)
        return cache.get(kid or "")

    return fetch


_verifier: Verifier | None = None


def set_verifier(fn: Verifier | None) -> None:
    """Tests inject a fake verifier (``None`` restores the production one)."""
    global _verifier
    _verifier = fn


def _default_verifier() -> Verifier:
    fetcher = securetoken_cert_fetcher()

    def verify(token: str) -> dict[str, Any]:
        return verify_firebase_token(token, project_id(), fetcher)

    return verify


def verify(token: str) -> dict[str, Any]:
    """Verify with the injected verifier, else the production one (built lazily, cached)."""
    global _verifier
    if _verifier is None:
        _verifier = _default_verifier()
    return _verifier(token)
