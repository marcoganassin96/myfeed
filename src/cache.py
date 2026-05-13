import os
import json
import redis
from fields import EnvVar

_client = None


def get_client():
    global _client
    if _client is None:
        _client = redis.Redis(
            host=os.environ[EnvVar.REDIS_HOST],
            port=int(os.environ.get(EnvVar.REDIS_PORT, "6379")),
            ssl=os.environ.get(EnvVar.REDIS_SSL, "false").lower() == "true",
            decode_responses=True,
        )
    return _client


def cache_get(key: str):
    raw = get_client().get(key)
    return None if raw is None else json.loads(raw)


def cache_set(key: str, value, ttl: int = 3600):
    get_client().setex(key, ttl, json.dumps(value, default=str))
