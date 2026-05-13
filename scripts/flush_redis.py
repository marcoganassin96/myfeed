#!/usr/bin/env python3
"""
Flush all Redis keys — ensures Redis is empty before cold-start scenarios.

Usage:
  CONFIG=config/dev.yaml python scripts/flush_redis.py
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from config import load as _cfg
from tunnel import ssm_tunnel, Service
from utils import timed
import redis


def _redis_client(host=None, port=None):
    cfg = _cfg()["redis"]
    use_ssl = cfg["ssl"]
    tunnelled = host is not None
    return redis.Redis(
        host=host or cfg["host"],
        port=port or cfg["port"],
        ssl=use_ssl,
        ssl_cert_reqs=None if tunnelled else "required",
        ssl_check_hostname=not tunnelled,
        decode_responses=True,
        socket_timeout=10,
        socket_connect_timeout=10,
    )


def _flush(rc) -> None:
    with timed("FLUSHALL"):
        rc.flushall()
    print("✓ Redis flushed", file=sys.stderr)
    rc.close()


if __name__ == "__main__":
    _env = os.environ.get("env", "local")
    with timed("Total time:"):
        if _env == "local":
            _flush(_redis_client())
        else:
            with ssm_tunnel(Service.REDIS) as (r_host, r_port):
                _flush(_redis_client(r_host, r_port))
