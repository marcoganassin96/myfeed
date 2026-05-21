import os

import redis.asyncio as aioredis

from fields import EnvVar


async def create_redis() -> aioredis.Redis:
    ssl = os.environ.get(EnvVar.REDIS_SSL, "false").lower() == "true"
    return aioredis.Redis(
        host=os.environ[EnvVar.REDIS_HOST],
        port=int(os.environ.get(EnvVar.REDIS_PORT, "6379")),
        decode_responses=True,
        ssl=ssl,
    )
