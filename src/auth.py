import functools
import json
import os
import urllib.request

from fastapi import HTTPException
from jose import JWTError, jwt

from fields import EnvVar


def _fetch_jwks() -> dict:
    region = os.environ[EnvVar.AWS_REGION]
    pool_id = os.environ[EnvVar.COGNITO_USER_POOL_ID]
    url = f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json"
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


@functools.lru_cache(maxsize=1)
def _jwks() -> dict:
    return _fetch_jwks()


def verify(token: str) -> str:
    try:
        header = jwt.get_unverified_header(token)
        keys = {k["kid"]: k for k in _jwks()["keys"]}
        key = keys.get(header.get("kid"))
        if key is None:
            raise HTTPException(status_code=401, detail="Unknown signing key")
        payload = jwt.decode(token, key, algorithms=["RS256"])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Missing sub claim")
        return sub
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
