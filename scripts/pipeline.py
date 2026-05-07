#!/usr/bin/env python3
"""
Full pre-load-test pipeline. Opens SSM tunnel once, then runs:
  1. 00_seed.py               — truncate + seed live DB
  2. 01_prewarm.py            — pre-warm Redis from seed result
  3. 02_create_test_tokens.py — create/refresh Cognito users, write tokens
  4. 03_get_load_test_ids.py  — query DB for newsletter/event IDs

Usage:
  CONFIG=config/dev.yaml DB_PASSWORD=<secret> python scripts/pipeline.py [--count N] [--skip-seed] [--skip-prewarm] [--skip-tokens]

After completion:
  source scripts/out/{env}/02_tokens.env
  source scripts/out/{env}/03_ids.env
"""
import argparse
import os
import pathlib
import subprocess
import sys

SCRIPTS = pathlib.Path(__file__).parent
sys.path.insert(0, str(SCRIPTS))

from paths import SEED_SCRIPT, PREWARM_SCRIPT, TOKENS_SCRIPT, IDS_SCRIPT, get_out_filepath, OutFile  # noqa: E402
from tunnel import ssm_tunnel, Service  # noqa: E402
from config import load as _cfg  # noqa: E402
from utils import timed  # noqa: E402

parser = argparse.ArgumentParser(description="Pre-load-test pipeline")
parser.add_argument("--count", type=int, default=20, help="IDs to fetch for k6 (default: 20)")
parser.add_argument("--skip-seed", action="store_true", help="Skip 00_seed.py (DB already seeded)")
parser.add_argument("--skip-prewarm", action="store_true", help="Skip 01_prewarm.py (Redis already warm)")
parser.add_argument("--skip-tokens", action="store_true", help="Skip token creation")
args = parser.parse_args()


def run(script: pathlib.Path, env: dict, extra: list[str] | None = None):
    cmd = [sys.executable, str(script)] + (extra or [])
    print(f"\n=== {script} ===", file=sys.stderr)
    with timed(script.name):
        result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        print(f"✗ {script} failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)


_env = os.environ.get("env", "local")

with timed("Total time:"):
    if _env == "local":
        if not args.skip_seed:
            run(SEED_SCRIPT, os.environ)
        if not args.skip_prewarm:
            run(PREWARM_SCRIPT, os.environ)
        if not args.skip_tokens:
            run(TOKENS_SCRIPT, os.environ)
        run(IDS_SCRIPT, os.environ, ["--count", str(args.count)])
    else:
        with ssm_tunnel(Service.DB) as (host, port):
            # BASTION_ID cleared so child scripts skip opening a second tunnel.
            tunnelled_env = {**os.environ, "DB_HOST": host, "DB_PORT": str(port), "BASTION_ID": ""}
            if not args.skip_seed:
                run(SEED_SCRIPT, tunnelled_env)
            # prewarm manages its own Redis tunnel
            if not args.skip_prewarm:
                run(PREWARM_SCRIPT, os.environ)
            if not args.skip_tokens:
                run(TOKENS_SCRIPT, os.environ)
            run(IDS_SCRIPT, tunnelled_env, ["--count", str(args.count)])

print("\n✓ Pipeline complete.", file=sys.stderr)
print(f"  source {get_out_filepath(_env, OutFile.TOKENS_ENV)}", file=sys.stderr)
print(f"  source {get_out_filepath(_env, OutFile.IDS_ENV)}", file=sys.stderr)
