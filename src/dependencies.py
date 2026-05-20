import httpx
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

import auth

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_mdg_client(request: Request) -> httpx.AsyncClient | None:
    return getattr(request.app.state, "mdg_client", None)


async def get_user_id(token: str = Depends(oauth2_scheme)) -> str:
    return auth.verify(token)
