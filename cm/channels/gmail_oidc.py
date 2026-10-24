"""Lane M: verify the Google-signed OIDC JWT on a Pub/Sub push request (pure, injectable key fetcher).

The webhook route passes ``Authorization: Bearer <jwt>``. We check signature (RS256), issuer, audience
(PUBSUB_PUSH_AUDIENCE), expiry, and that the signing service account is the expected one
(PUBSUB_PUSH_SA_EMAIL, email_verified true). No network here: ``key_fetcher(kid)`` returns the public key
(PEM string/bytes or a key object). ``google_cert_fetcher`` is the production fetcher; it is never called
in tests and only runs when the webhook is wired.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import jwt

GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"
KeyFetcher = Callable[[str | None], Any]


class PushAuthError(Exception):
    """The push request is not authentic. ``reason`` is a short code, safe to log."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise PushAuthError("missing_bearer")
    return authorization[7:].strip()


def verify_push_jwt(token: str, *, audience: str, expected_email: str, key_fetcher: KeyFetcher,
                    leeway_s: int = 30, now: float | None = None) -> dict[str, Any]:
    """Return the claims or raise PushAuthError. Fails closed on any problem."""
    if not audience or not expected_email:
        raise PushAuthError("not_configured")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise PushAuthError("malformed") from exc
    if header.get("alg") != "RS256":
        raise PushAuthError("bad_alg")
    try:
        key = key_fetcher(header.get("kid"))
    except Exception as exc:  # noqa: BLE001
        raise PushAuthError("key_unavailable") from exc
    if key is None:
        raise PushAuthError("unknown_kid")
    opts: dict[str, Any] = {"require": ["exp", "iss", "aud"]}
    kwargs: dict[str, Any] = {}
    if now is not None:  # deterministic clock for tests: validate exp/iat manually
        opts.update(verify_exp=False, verify_iat=False, verify_nbf=False)
    try:
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=audience, leeway=leeway_s,
                            options=opts, **kwargs)
    except jwt.ExpiredSignatureError as exc:
        raise PushAuthError("expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise PushAuthError("bad_audience") from exc
    except jwt.PyJWTError as exc:
        raise PushAuthError("invalid_signature_or_claims") from exc
    if now is not None and claims["exp"] + leeway_s < now:
        raise PushAuthError("expired")
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise PushAuthError("bad_issuer")
    if str(claims.get("email", "")).lower() != expected_email.lower() or claims.get("email_verified") is not True:
        raise PushAuthError("bad_email")
    return claims


def google_cert_fetcher(http_get: Callable[[str], bytes] | None = None) -> KeyFetcher:
    """Production key fetcher (Google's x509 certs by kid). Cached per process. Network on first use only."""
    cache: dict[str, Any] = {}

    def fetch(kid: str | None) -> Any:
        if not cache or kid not in cache:
            if http_get is None:
                import httpx

                raw = httpx.get(GOOGLE_CERTS_URL, timeout=5.0).content
            else:
                raw = http_get(GOOGLE_CERTS_URL)
            from cryptography.x509 import load_pem_x509_certificate

            cache.clear()
            for k, pem in json.loads(raw).items():
                cache[k] = load_pem_x509_certificate(pem.encode()).public_key()
        return cache.get(kid or "")

    return fetch
