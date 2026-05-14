import asyncpg
import redis.asyncio as aioredis
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

import auth

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


async def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


async def get_user_id(token: str = Depends(oauth2_scheme)) -> str:
    return auth.verify(token)
