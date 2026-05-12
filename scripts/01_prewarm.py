#!/usr/bin/env python3
"""
Pre-warms Redis from seed result written by 00_seed.py.

Usage:
  CONFIG=config/dev.yaml python scripts/01_prewarm.py [--n N]

Options:
  --n N   Number of most-recent newsletters to warm (0 = all, default: 0)

Env vars:
  CONFIG  path to YAML config file (default: config/local.yaml)
"""
import argparse, os, sys, json, pathlib
from dataclasses import dataclass
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from paths import get_out_filepath, OutFile
from models import SeedResult
import redis
from tunnel import ssm_tunnel, Service
from config import load as _cfg
from utils import timed


@dataclass
class CacheCoverage:
    cached: int
    total: int

    @property
    def pct(self) -> float:
        return 100.0 * self.cached / self.total if self.total else 0.0

    def __str__(self) -> str:
        return f"{self.cached}/{self.total} ({self.pct:.1f}%)"


def get_cache_coverage(rc, total: int) -> CacheCoverage:
    cached = sum(1 for _ in rc.scan_iter(match="newsletter:*"))
    return CacheCoverage(cached=cached, total=total)


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
        socket_timeout=10,
        socket_connect_timeout=10,
    )


def prewarm_redis(rc, payload: SeedResult, n: int = 0) -> None:
    """Warms the n most-recent newsletters into Redis. n=0 warms all."""
    print("Pre-warming Redis...")
    with timed("Flushed redis"):
        rc.flushall()

    entries = sorted(
        payload.nl_ids.items(),
        key=lambda kv: kv[0].split("|")[1],
        reverse=True,
    )
    if n > 0:
        entries = entries[:n]

    with timed(f"Pre-warmed {len(entries)} keys"):
        with rc.pipeline(transaction=False) as pipe:
            for key, nl_id in entries:
                date_str = key.split("|")[1]
                pipe.set(
                    f"newsletter:{nl_id}",
                    json.dumps({"newsletter_id": str(nl_id), "date": date_str}),
                    ex=REDIS_TTL,
                )
            pipe.execute()
    print("✓ Redis pre-warm complete")


def _run_redis(rc, env: str, n: int = 0) -> CacheCoverage:
    out_path = get_out_filepath(env, OutFile.SEED_RESULT)
    payload = SeedResult.model_validate_json(out_path.read_text())
    try:
        prewarm_redis(rc, payload, n)
    except Exception as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        cov = get_cache_coverage(rc, total=len(payload.nl_ids))
        print(f"✓ Redis coverage: {cov}")
        rc.close()
    return cov


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=0, metavar="N",
                        help="Most-recent newsletters to warm (0 = all, default: 0)")
    args = parser.parse_args()
    _env = os.environ.get("env", "local")
    with timed("Total time:"):
        if _env == "local":
            _run_redis(redis_client(), _env, args.n)
        else:
            with ssm_tunnel(Service.REDIS) as (r_host, r_port):
                _run_redis(redis_client(r_host, r_port), _env, args.n)
