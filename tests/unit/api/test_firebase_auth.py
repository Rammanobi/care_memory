"""Firebase ID token verifier (cm/api/firebase_auth.py): local RSA keys, no network, no DB."""

import datetime as dt
import json
import time
from typing import Any

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from cm.api import firebase_auth as fa

PROJECT = "demo-project"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def fetcher(kid: str | None) -> Any:
    return KEY.public_key() if kid == "k1" else None


def token(*, aud: str = PROJECT, iss: str | None = None, exp_in: int = 300, key: Any = KEY,
          sub: str = "uid-1", provider: str = "password", kid: str = "k1", iat_off: int = -10,
          **extra: Any) -> str:
    now = int(time.time())
    claims = {"aud": aud, "iss": iss or f"https://securetoken.google.com/{PROJECT}", "sub": sub,
              "iat": now + iat_off, "auth_time": now + iat_off, "exp": now + exp_in,
              "firebase": {"sign_in_provider": provider}, **extra}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def test_good_token_returns_claims() -> None:
    c = fa.verify_firebase_token(token(role="doctor", pid="p", tv=1), PROJECT, fetcher)
    assert c["sub"] == "uid-1" and c["role"] == "doctor"


@pytest.mark.parametrize(
    ("tok", "reason"),
    [
        ("not-a-jwt", "malformed"),
        (token(kid="nope"), "unknown_kid"),
        (token(aud="other-project"), "bad_audience"),
        (token(iss="https://securetoken.google.com/other-project"), "bad_issuer"),
        (token(exp_in=-600), "expired"),
        (token(iat_off=600, exp_in=900), "issued_in_future"),
        (token(sub=""), "invalid_signature_or_claims"),
        (token(provider="anonymous"), "bad_provider"),
        (token(key=OTHER), "invalid_signature_or_claims"),
    ],
)
def test_bad_tokens_fail_closed(tok: str, reason: str) -> None:
    with pytest.raises(fa.FirebaseAuthError) as e:
        fa.verify_firebase_token(tok, PROJECT, fetcher)
    assert e.value.reason in {reason, "empty_sub"}


def test_wrong_algorithms_refused() -> None:
    now = int(time.time())
    body = {"aud": PROJECT, "iss": f"https://securetoken.google.com/{PROJECT}", "sub": "u",
            "iat": now, "exp": now + 99}
    for tok in (jwt.encode(body, "secret-for-test-only-0123456789abcdef", algorithm="HS256"),
                jwt.encode(body, "", algorithm="none")):
        with pytest.raises(fa.FirebaseAuthError) as e:
            fa.verify_firebase_token(tok, PROJECT, fetcher)
        assert e.value.reason == "bad_alg"


def test_unconfigured_and_fetch_failure_fail_closed() -> None:
    with pytest.raises(fa.FirebaseAuthError, match="not_configured"):
        fa.verify_firebase_token(token(), "", fetcher)

    def boom(kid: str | None) -> Any:
        raise OSError("network down")

    with pytest.raises(fa.FirebaseAuthError, match="key_unavailable"):
        fa.verify_firebase_token(token(), PROJECT, boom)


def _cert_pem(key: Any) -> str:
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    now = dt.datetime.now(dt.UTC)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=1))
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def test_securetoken_fetcher_parses_and_caches() -> None:
    calls: list[str] = []

    def http_get(url: str) -> tuple[bytes, str]:
        calls.append(url)
        return json.dumps({"k1": _cert_pem(KEY)}).encode(), "public, max-age=600"

    f = fa.securetoken_cert_fetcher(http_get)
    assert fa.verify_firebase_token(token(), PROJECT, f)["sub"] == "uid-1"
    assert f("k1") is not None
    assert len(calls) == 1 and calls[0] == fa.SECURETOKEN_CERTS_URL


def test_mode_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTH_MODE", raising=False)
    assert fa.mode() == "local"
    fa.check_config()  # local needs nothing
    monkeypatch.setenv("AUTH_MODE", "firebase")
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    with pytest.raises(RuntimeError):
        fa.check_config()
    monkeypatch.setenv("FIREBASE_PROJECT_ID", PROJECT)
    fa.check_config()
