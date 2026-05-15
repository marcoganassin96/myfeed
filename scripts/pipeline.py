#!/usr/bin/env python3
"""
Full load-test pipeline. Supports --runtime lambda (default) and --runtime fargate.

Lambda steps:   seed → tokens → ids → smoke → flush → uncached → prewarm → cached → sse → mixed → stress
Fargate steps:  scale_up → seed → tokens → ids → smoke → flush → uncached → prewarm
                → cached → sse → mixed → benchmark → scale_down

Deploy (build + push image to ECR) is a separate step run before the pipeline:
  bash scripts/deploy_fargate.sh

scale_down always runs when scale_up is in the step list (try/finally).

Usage:
  CONFIG=config/dev.yaml DB_PASSWORD=<secret> python scripts/pipeline.py [--runtime fargate] [--from-step smoke]
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
    SCALE_UP_SCRIPT, SCALE_DOWN_SCRIPT,
    get_out_filepath, OutFile,
)
from tunnel import ssm_tunnel, Service          # noqa: E402
from utils import timed, die                   # noqa: E402
from models import SeedResult                  # noqa: E402
from steps import Step, STEP_ORDER, FARGATE_STEP_ORDER, K6_SCRIPTS, DB_STEPS  # noqa: E402
from run_load_tests import run_k6, preflight_k6, load_k6_vars  # noqa: E402


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
    return 90


def _build_runners(
    runtime: str, db_env: dict, _env: str
) -> dict[Step, Callable[[], None]]:
    runners: dict[Step, Callable[[], None]] = {
        Step.SEED:    lambda: run_script(SEED_SCRIPT, db_env),
        Step.TOKENS:  lambda: run_script(TOKENS_SCRIPT, os.environ),
        Step.IDS:     lambda: run_script(IDS_SCRIPT, db_env, ["--count", str(_ids_count(_env))]),
        Step.FLUSH:   lambda: run_script(FLUSH_SCRIPT, os.environ),
        Step.PREWARM: lambda: run_script(PREWARM_SCRIPT, os.environ),
    }
    for step in K6_SCRIPTS:
        runners[step] = lambda s=step, e=_env, rt=runtime: run_k6(s, load_k6_vars(e, runtime=rt))

    if runtime == "fargate":
        runners[Step.SCALE_UP]   = lambda: run_script(SCALE_UP_SCRIPT, os.environ)
        runners[Step.SCALE_DOWN] = lambda: run_script(SCALE_DOWN_SCRIPT, os.environ)

    return runners


def _run_pipeline_steps(steps: list[Step], runners: dict[Step, Callable[[], None]]) -> None:
    for step in steps:
        runners[step]()


def run_pipeline(steps: list[Step], runtime: str, db_env: dict, _env: str) -> None:
    preflight_k6(steps, _env, runtime=runtime)
    runners = _build_runners(runtime, db_env, _env)

    if runtime == "fargate" and Step.SCALE_UP in steps:
        non_scale_down = [s for s in steps if s != Step.SCALE_DOWN]
        try:
            _run_pipeline_steps(non_scale_down, runners)
        finally:
            runners[Step.SCALE_DOWN]()
    else:
        _run_pipeline_steps(steps, runners)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--runtime",
        choices=["lambda", "fargate"],
        default="lambda",
        help="Pipeline runtime. Default: lambda",
    )
    parser.add_argument(
        "--from-step",
        metavar="STEP",
        help=f"Resume from STEP. Lambda choices: {', '.join(STEP_ORDER)}  Fargate choices: {', '.join(FARGATE_STEP_ORDER)}",
    )
    return parser.parse_args()


def _select_steps(from_step: str | None, runtime: str) -> list[Step]:
    order = FARGATE_STEP_ORDER if runtime == "fargate" else STEP_ORDER
    if from_step:
        s = Step(from_step)
        if s not in order:
            die(f"Step '{from_step}' is not in the {runtime} pipeline. "
                f"Valid steps: {', '.join(order)}")
        return order[order.index(s):]
    return list(order)


def _run_with_tunnel(steps: list[Step], runtime: str, _env: str) -> None:
    needs_db = bool(DB_STEPS & set(steps))
    if _env == "local" or not needs_db:
        run_pipeline(steps, runtime, os.environ, _env)
    else:
        with ssm_tunnel(Service.DB) as (host, port):
            tunnelled = {**os.environ, "DB_HOST": host, "DB_PORT": str(port), "BASTION_ID": ""}
            run_pipeline(steps, runtime, tunnelled, _env)


def _print_completion_hints(steps: list[Step], _env: str) -> None:
    if Step.TOKENS in steps:
        print(f"  source {get_out_filepath(_env, OutFile.TOKENS_ENV)}", file=sys.stderr)
    if Step.IDS in steps:
        print(f"  source {get_out_filepath(_env, OutFile.IDS_ENV)}", file=sys.stderr)


def main() -> None:
    args = _parse_args()
    steps = _select_steps(args.from_step, args.runtime)
    _env = os.environ.get("env", "local")
    print(f"\nRuntime: {args.runtime}  Steps: {' → '.join(steps)}", file=sys.stderr)
    _run_with_tunnel(steps, args.runtime, _env)
    print(f"\n✓ Pipeline complete.", file=sys.stderr)
    _print_completion_hints(steps, _env)


if __name__ == "__main__":
    with timed("Total time:"):
        main()
