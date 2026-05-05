#!/usr/bin/env python3
"""
Full pre-load-test pipeline. Opens SSM tunnel once, then runs:
  1. seed.py                  — truncate + seed live DB + pre-warm Redis
  2. 00_create_test_tokens.py — create/refresh Cognito users, write tokens
  3. 01_get_load_test_ids.py  — query DB for newsletter/event IDs

Usage:
  source .env
  python scripts/pipeline.py [--count N] [--skip-seed] [--skip-tokens]

After completion:
  source scripts/out/00_tokens.env
  source scripts/out/01_ids.env
"""
import argparse
import os
import pathlib
import subprocess
import sys

SCRIPTS = pathlib.Path(__file__).parent
sys.path.insert(0, str(SCRIPTS))

from tunnel import ssm_tunnel  # noqa: E402

parser = argparse.ArgumentParser(description="Pre-load-test pipeline")
parser.add_argument("--count", type=int, default=20, help="IDs to fetch for k6 (default: 20)")
parser.add_argument("--skip-seed", action="store_true", help="Skip seed.py (DB already seeded)")
parser.add_argument("--skip-tokens", action="store_true", help="Skip token creation")
args = parser.parse_args()


def run(script: str, env: dict, extra: list[str] | None = None):
    cmd = [sys.executable, str(SCRIPTS / script)] + (extra or [])
    print(f"\n=== {script} ===", file=sys.stderr)
    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        print(f"✗ {script} failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)


with ssm_tunnel() as (host, port):
    # Subprocesses inherit tunnel's host/port; BASTION_ID cleared so they skip
    # opening a second tunnel via their own ssm_tunnel() call.
    tunnelled_env = {**os.environ, "DB_HOST": host, "DB_PORT": str(port), "BASTION_ID": ""}

    if not args.skip_seed:
        run("seed.py", tunnelled_env)

    if not args.skip_tokens:
        run("00_create_test_tokens.py", os.environ)  # Cognito only, no DB

    run("01_get_load_test_ids.py", tunnelled_env, ["--count", str(args.count)])

print("\n✓ Pipeline complete.", file=sys.stderr)
print("  source scripts/out/00_tokens.env", file=sys.stderr)
print("  source scripts/out/01_ids.env", file=sys.stderr)
