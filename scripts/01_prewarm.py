#!/usr/bin/env python3
"""
Pre-warms Redis from seed result written by 00_seed.py.

Usage:
  CONFIG=config/dev.yaml python scripts/01_prewarm.py

Env vars:
  CONFIG  path to YAML config file (default: config/local.yaml)
"""
import os, sys, json, pathlib
from datetime import timedelta
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from paths import get_out_filepath, OutFile
from models import SeedResult
import redis
from tunnel import ssm_redis_tunnel
from config import load as _cfg
from utils import timed

DAYS = 30
REDIS_TTL = 3600


def redis_client(host: str | None = None, port: int | None = None):
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
    )


def prewarm_redis(rc, env: str) -> None:
    out_path = get_out_filepath(env, OutFile.SEED_RESULT)
    payload = SeedResult.model_validate_json(out_path.read_text())

    print("Pre-warming Redis...")
    with timed("Flushed redis"):
        rc.flushall()
    latest_date_str = str(payload.start + timedelta(days=DAYS - 1))
    with timed("Pre-warmed Redis"):
        with rc.pipeline(transaction=False) as pipe:
            for tid in payload.topic_ids:
                nl_id = payload.nl_ids.get(f"{tid}|{latest_date_str}")
                if nl_id:
                    pipe.set(f"newsletter:{nl_id}", json.dumps({"newsletter_id": str(nl_id), "date": latest_date_str}), ex=REDIS_TTL)
            pipe.execute()
    print("✓ Redis pre-warm complete")


def _run_redis(rc, env: str) -> None:
    try:
        prewarm_redis(rc, env)
    except Exception as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        rc.close()


if __name__ == "__main__":
    _env = os.environ.get("env", "local")
    with timed("Total time:"):
        if _env == "local":
            _run_redis(redis_client(), _env)
        else:
            with ssm_redis_tunnel() as (r_host, r_port):
                _run_redis(redis_client(r_host, r_port), _env)
