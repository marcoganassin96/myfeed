import pytest
from unittest.mock import patch
from fastapi import HTTPException
from jose import JWTError


def test_verify_returns_sub_on_valid_token():
    import auth
    with patch("auth._fetch_jwks", return_value={"keys": [{"kid": "k1", "kty": "RSA"}]}):
        auth._jwks.cache_clear()
        with patch("auth.jwt.get_unverified_header", return_value={"kid": "k1"}):
            with patch("auth.jwt.decode", return_value={"sub": "user-123"}):
                assert auth.verify("valid.token.here") == "user-123"


def test_verify_raises_401_on_unknown_kid():
    import auth
    with patch("auth._fetch_jwks", return_value={"keys": [{"kid": "other-kid"}]}):
        auth._jwks.cache_clear()
        with patch("auth.jwt.get_unverified_header", return_value={"kid": "unknown"}):
            with pytest.raises(HTTPException) as exc:
                auth.verify("bad.token")
            assert exc.value.status_code == 401


def test_verify_raises_401_on_jwt_error():
    import auth
    with patch("auth._fetch_jwks", return_value={"keys": [{"kid": "k1"}]}):
        auth._jwks.cache_clear()
        with patch("auth.jwt.get_unverified_header", return_value={"kid": "k1"}):
            with patch("auth.jwt.decode", side_effect=JWTError("expired")):
                with pytest.raises(HTTPException) as exc:
                    auth.verify("expired.token")
                assert exc.value.status_code == 401


def test_verify_raises_401_on_missing_sub():
    import auth
    with patch("auth._fetch_jwks", return_value={"keys": [{"kid": "k1"}]}):
        auth._jwks.cache_clear()
        with patch("auth.jwt.get_unverified_header", return_value={"kid": "k1"}):
            with patch("auth.jwt.decode", return_value={}):
                with pytest.raises(HTTPException) as exc:
                    auth.verify("no-sub.token")
                assert exc.value.status_code == 401
