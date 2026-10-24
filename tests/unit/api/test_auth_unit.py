"""Password hashing (scrypt) and JWT round trip."""

import jwt
import pytest

from cm.api import auth
from cm.api.routers.query import verify_numbers
from cm.contracts.agents import ToolCallUsed


def test_password_hash_roundtrip() -> None:
    h = auth.hash_password("correct horse")
    assert h.startswith("scrypt$")
    assert auth.verify_password("correct horse", h)
    assert not auth.verify_password("wrong", h)
    assert not auth.verify_password("x", "garbage")


def test_token_roundtrip_and_tamper() -> None:
    tok = auth.create_access_token({"sub": "u", "role": "doctor", "person_id": "p", "tv": 1})
    claims = auth.decode_access_token(tok)
    assert claims["role"] == "doctor" and claims["exp"] > claims["iat"] and claims["jti"]
    with pytest.raises(jwt.PyJWTError):
        auth.decode_access_token(tok[:-3] + "abc")


def test_number_check_accepts_only_numbers_in_rows() -> None:
    call = ToolCallUsed(
        n=1, tool="t", args={}, row_count=2, result_preview=[{"code": "PT-0142", "day": 60}]
    )
    assert verify_numbers("PT-0142 is on day 60 [1].", [call])
    assert not verify_numbers("PT-0142 is on day 61 [1].", [call])
