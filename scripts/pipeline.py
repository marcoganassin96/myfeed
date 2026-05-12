#!/usr/bin/env python3
"""
Full load-test pipeline: data setup then k6 scenarios in progressive order.

Each step is a hard gate — non-zero exit stops the pipeline immediately.

Steps (in order):
  seed    — truncate + seed live DB
  tokens  — create/refresh Cognito tokens
  ids     — fetch newsletter/event IDs for k6
  smoke   — 1 VU sanity check across all endpoints
  cold    — newsletter_cold.js  (Redis still empty — runs before prewarm)
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
import shutil
import subprocess
import sys
from enum import StrEnum
from typing import Callable

SCRIPTS = pathlib.Path(__file__).parent
sys.path.insert(0, str(SCRIPTS))

from paths import (  # noqa: E402
    ROOT_DIR, SEED_SCRIPT, PREWARM_SCRIPT, TOKENS_SCRIPT, IDS_SCRIPT,
    get_out_filepath, OutFile,
)
from tunnel import ssm_tunnel, Service  # noqa: E402
from config import load as _cfg  # noqa: E402
from utils import timed  # noqa: E402
from models import SeedResult  # noqa: E402

LOAD_TESTS = ROOT_DIR / "load_tests"


class Step(StrEnum):
    SEED    = "seed"
    TOKENS  = "tokens"
    IDS     = "ids"
    SMOKE   = "smoke"
    COLD    = "cold"
    PREWARM = "prewarm"
    CACHED  = "cached"
    SSE     = "sse"
    MIXED   = "mixed"
    STRESS  = "stress"


STEP_ORDER: list[Step] = [
    Step.SEED, Step.TOKENS, Step.IDS,
    Step.SMOKE, Step.COLD, Step.PREWARM,
    Step.CACHED, Step.SSE, Step.MIXED, Step.STRESS,
]

K6_SCRIPTS: dict[Step, tuple[str, str]] = {
    Step.SMOKE:  ("smoke.js",             "1 VU · sanity check"),
    Step.COLD:   ("newsletter_cold.js",   "200 VUs · p99<300ms"),
    Step.CACHED: ("newsletter_cached.js", "500 VUs · p99<50ms"),
    Step.SSE:    ("deep_dive_sse.js",     "50 VUs · first chunk<500ms"),
    Step.MIXED:  ("mixed_realistic.js",   "1000 VUs · p95<200ms"),
    Step.STRESS: ("cold_start_stress.js", "spike 0→1000 VUs · errors<1%"),
}

DB_STEPS = {Step.SEED, Step.IDS}


def die(msg: str) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(1)


def run_script(script: pathlib.Path, env: dict, extra: list[str] | None = None) -> None:
    cmd = [sys.executable, str(script)] + (extra or [])
    print(f"\n=== {script.name} ===", file=sys.stderr)
    with timed(script.name):
        r = subprocess.run(cmd, env=env)
    if r.returncode != 0:
        die(f"{script.name} failed (exit {r.returncode})")


def parse_env_file(path: pathlib.Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


def load_k6_vars(_env: str) -> dict[str, str]:
    tokens_env = parse_env_file(get_out_filepath(_env, OutFile.TOKENS_ENV))
    ids_env    = parse_env_file(get_out_filepath(_env, OutFile.IDS_ENV))
    token = os.environ.get("COGNITO_TOKEN") or tokens_env.get("COGNITO_TOKEN", "")
    if not token:
        tokens_txt = get_out_filepath(_env, OutFile.TOKENS_TXT)
        if tokens_txt.exists():
            lines = [ln.strip() for ln in tokens_txt.read_text().splitlines() if ln.strip()]
            token = lines[0] if lines else ""
    return {
        "API_URL":        os.environ.get("API_URL") or _cfg()["api"]["url"],
        "COGNITO_TOKEN":  token,
        "NEWSLETTER_IDS": os.environ.get("NEWSLETTER_IDS") or ids_env.get("NEWSLETTER_IDS", ""),
        "EVENT_IDS":      os.environ.get("EVENT_IDS") or ids_env.get("EVENT_IDS", ""),
    }


def k6_binary() -> str:
    path = shutil.which("k6")
    if path is None:
        die("k6 not found in PATH — install from https://k6.io/docs/getting-started/installation/")
    return path  # type: ignore[return-value]


def run_k6(step: Step, k6_vars: dict[str, str]) -> None:
    script_name, description = K6_SCRIPTS[step]
    script_path = LOAD_TESTS / script_name
    if not script_path.exists():
        die(f"k6 script not found: {script_path}")
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  {step}  —  {description}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    cmd = [
        k6_binary(), "run",
        "-e", f"API_URL={k6_vars['API_URL']}",
        "-e", f"COGNITO_TOKEN={k6_vars['COGNITO_TOKEN']}",
        "-e", f"NEWSLETTER_IDS={k6_vars['NEWSLETTER_IDS']}",
        "-e", f"EVENT_IDS={k6_vars['EVENT_IDS']}",
        str(script_path),
    ]
    with timed(str(step)):
        r = subprocess.run(cmd)
    if r.returncode != 0:
        die(f"k6 scenario '{step}' failed (exit {r.returncode})")


def _ids_count(_env: str) -> int:
    seed_path = get_out_filepath(_env, OutFile.SEED_RESULT)
    if seed_path.exists():
        try:
            payload = SeedResult.model_validate_json(seed_path.read_text())
            return len(payload.nl_ids)
        except Exception:
            pass
    return 90  # fallback: 3 topics × 30 days


def _preflight_k6(steps: list[Step], _env: str) -> dict[str, str]:
    """Load and validate k6 vars if any k6 step is scheduled. Returns {} otherwise."""
    if not any(s in K6_SCRIPTS for s in steps):
        return {}
    k6_vars = load_k6_vars(_env)
    missing = [k for k, v in k6_vars.items() if not v]
    if missing:
        die(f"Missing k6 vars: {', '.join(missing)} — run seed/tokens/ids steps first")
    print(f"\nAPI: {k6_vars['API_URL']}", file=sys.stderr)
    print(f"Token: {k6_vars['COGNITO_TOKEN'][:20]}...", file=sys.stderr)
    print(
        f"Newsletter IDs: {len(k6_vars['NEWSLETTER_IDS'].split(','))}"
        f"  Event IDs: {len(k6_vars['EVENT_IDS'].split(','))}",
        file=sys.stderr,
    )
    return k6_vars


def _build_runners(
    db_env: dict, k6_vars: dict[str, str], _env: str
) -> dict[Step, Callable[[], None]]:
    runners: dict[Step, Callable[[], None]] = {
        Step.SEED:    lambda: run_script(SEED_SCRIPT, db_env),
        Step.TOKENS:  lambda: run_script(TOKENS_SCRIPT, os.environ),
        Step.IDS:     lambda: run_script(IDS_SCRIPT, db_env, ["--count", str(_ids_count(_env))]),
        Step.PREWARM: lambda: run_script(PREWARM_SCRIPT, os.environ),
    }
    for step in K6_SCRIPTS:
        runners[step] = lambda s=step: run_k6(s, k6_vars)
    return runners


def run_pipeline(steps: list[Step], db_env: dict, _env: str) -> None:
    k6_vars = _preflight_k6(steps, _env)
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
