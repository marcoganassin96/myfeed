#!/usr/bin/env python3
"""
Full load-test pipeline: data setup then k6 scenarios in progressive order.

Each step is a hard gate — non-zero exit stops the pipeline immediately.

Steps (in order):
  seed    — truncate + seed live DB
  tokens  — create/refresh Cognito tokens
  ids     — fetch newsletter/event IDs for k6
  smoke   — 1 VU sanity check across all endpoints
  flush   — FLUSHALL Redis (guarantees cold cache for cold scenario)
  cold    — newsletter_cold.js  (Redis empty — runs after flush, before prewarm)
  prewarm — pre-warm Redis + 100% coverage assertion
  cached  — newsletter_cached.js  (500 VUs, Redis warm)
  sse     — deep_dive_sse.js
  mixed   — mixed_realistic.js
  stress  — cold_start_stress.js

Usage:
  CONFIG=config/dev.yaml DB_PASSWORD=<secret> python scripts/pipeline.py [--from-step STEP]
"""
import argparse
import os
import pathlib
import subprocess
import sys
from typing import Callable

SCRIPTS = pathlib.Path(__file__).parent
sys.path.insert(0, str(SCRIPTS))

from paths import (  # noqa: E402
    SEED_SCRIPT, PREWARM_SCRIPT, TOKENS_SCRIPT, IDS_SCRIPT, FLUSH_SCRIPT,
    get_out_filepath, OutFile,
)
from tunnel import ssm_tunnel, Service          # noqa: E402
from utils import timed, die                   # noqa: E402
from models import SeedResult                  # noqa: E402
from steps import Step, STEP_ORDER, K6_SCRIPTS, DB_STEPS  # noqa: E402
from run_load_tests import run_k6, preflight_k6            # noqa: E402


def run_script(script: pathlib.Path, env: dict, extra: list[str] | None = None) -> None:
    cmd = [sys.executable, str(script)] + (extra or [])
    print(f"\n=== {script.name} ===", file=sys.stderr)
    with timed(script.name):
        r = subprocess.run(cmd, env=env)
    if r.returncode != 0:
        die(f"{script.name} failed (exit {r.returncode})")


def _ids_count(_env: str) -> int:
    seed_path = get_out_filepath(_env, OutFile.SEED_RESULT)
    if seed_path.exists():
        try:
            payload = SeedResult.model_validate_json(seed_path.read_text())
            return len(payload.nl_ids)
        except Exception:
            pass
    return 90  # fallback: 3 topics × 30 days


def _build_runners(
    db_env: dict, k6_vars: dict[str, str], _env: str
) -> dict[Step, Callable[[], None]]:
    runners: dict[Step, Callable[[], None]] = {
        Step.SEED:    lambda: run_script(SEED_SCRIPT, db_env),
        Step.TOKENS:  lambda: run_script(TOKENS_SCRIPT, os.environ),
        Step.IDS:     lambda: run_script(IDS_SCRIPT, db_env, ["--count", str(_ids_count(_env))]),
        Step.FLUSH:   lambda: run_script(FLUSH_SCRIPT, os.environ),
        Step.PREWARM: lambda: run_script(PREWARM_SCRIPT, os.environ),
    }
    for step in K6_SCRIPTS:
        runners[step] = lambda s=step: run_k6(s, k6_vars)
    return runners


def run_pipeline(steps: list[Step], db_env: dict, _env: str) -> None:
    k6_vars = preflight_k6(steps, _env)
    runners = _build_runners(db_env, k6_vars, _env)
    for step in steps:
        runners[step]()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--from-step",
        choices=list(Step),
        metavar="STEP",
        help=f"Skip earlier steps and resume from STEP. Choices: {', '.join(Step)}",
    )
    return parser.parse_args()


def _select_steps(from_step: str | None) -> list[Step]:
    start_idx = STEP_ORDER.index(Step(from_step)) if from_step else 0
    return STEP_ORDER[start_idx:]


def _run_with_tunnel(steps: list[Step], _env: str) -> None:
    needs_db = bool(DB_STEPS & set(steps))
    if _env == "local" or not needs_db:
        run_pipeline(steps, os.environ, _env)
    else:
        with ssm_tunnel(Service.DB) as (host, port):
            tunnelled = {**os.environ, "DB_HOST": host, "DB_PORT": str(port), "BASTION_ID": ""}
            run_pipeline(steps, tunnelled, _env)


def _print_completion_hints(steps: list[Step], _env: str) -> None:
    if Step.TOKENS in steps:
        print(f"  source {get_out_filepath(_env, OutFile.TOKENS_ENV)}", file=sys.stderr)
    if Step.IDS in steps:
        print(f"  source {get_out_filepath(_env, OutFile.IDS_ENV)}", file=sys.stderr)


def main() -> None:
    args = _parse_args()
    steps = _select_steps(args.from_step)
    _env = os.environ.get("env", "local")
    print(f"\nSteps: {' → '.join(steps)}", file=sys.stderr)
    _run_with_tunnel(steps, _env)
    print(f"\n✓ Pipeline complete.", file=sys.stderr)
    _print_completion_hints(steps, _env)


if __name__ == "__main__":
    with timed("Total time:"):
        main()
