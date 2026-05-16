import os

import asyncpg

from fields import EnvVar


async def create_pool() -> asyncpg.Pool:
    ssl = os.environ.get(EnvVar.DB_SSL, "require")
    return await asyncpg.create_pool(
        host=os.environ[EnvVar.DB_HOST],
        port=int(os.environ.get(EnvVar.DB_PORT, "5432")),
        database=os.environ[EnvVar.DB_NAME],
        user=os.environ[EnvVar.DB_USER],
        password=os.environ[EnvVar.DB_PASSWORD],
        min_size=5,
        max_size=20,
        command_timeout=5,
        ssl=ssl,
    )
