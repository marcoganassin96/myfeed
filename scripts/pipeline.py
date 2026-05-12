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
    Step.SMOKE:  ("smoke.js",            "1 VU · sanity check"),
    Step.COLD:   ("newsletter_cold.js",  "200 VUs · p99<300ms"),
    Step.CACHED: ("newsletter_cached.js","500 VUs · p99<50ms"),
    Step.SSE:    ("deep_dive_sse.js",    "50 VUs · first chunk<500ms"),
    Step.MIXED:  ("mixed_realistic.js",  "1000 VUs · p95<200ms"),
    Step.STRESS: ("cold_start_stress.js","spike 0→1000 VUs · errors<1%"),
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


def load_k6_vars() -> dict[str, str]:
    _env = os.environ.get("env", "local")
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
    """Read newsletter count from seed result; fall back to 90 (3 topics × 30 days)."""
    seed_path = get_out_filepath(_env, OutFile.SEED_RESULT)
    if seed_path.exists():
        try:
            payload = SeedResult.model_validate_json(seed_path.read_text())
            return len(payload.nl_ids)
        except Exception:
            pass
    return 90


def main() -> None:
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
    args = parser.parse_args()

    start_idx = STEP_ORDER.index(Step(args.from_step)) if args.from_step else 0
    steps_to_run = STEP_ORDER[start_idx:]

    _env = os.environ.get("env", "local")
    needs_db_tunnel = bool(DB_STEPS & set(steps_to_run))

    print(f"\nSteps: {' → '.join(steps_to_run)}", file=sys.stderr)

    k6_vars: dict[str, str] = {}

    def execute(step: Step, db_env: dict) -> None:
        nonlocal k6_vars
        if step in K6_SCRIPTS and not k6_vars:
            k6_vars = load_k6_vars()
            missing = [k for k, v in k6_vars.items() if not v]
            if missing:
                die(f"Missing k6 vars: {', '.join(missing)} — run seed/tokens/ids steps first")
            print(f"\nAPI: {k6_vars['API_URL']}", file=sys.stderr)
            print(f"Token: {k6_vars['COGNITO_TOKEN'][:20]}...", file=sys.stderr)
            newsletter_count = len(k6_vars["NEWSLETTER_IDS"].split(","))
            event_count = len(k6_vars["EVENT_IDS"].split(","))
            print(f"Newsletter IDs: {newsletter_count}  Event IDs: {event_count}", file=sys.stderr)

        if step == Step.SEED:
            run_script(SEED_SCRIPT, db_env)
        elif step == Step.TOKENS:
            run_script(TOKENS_SCRIPT, os.environ)
        elif step == Step.IDS:
            count = _ids_count(_env)
            run_script(IDS_SCRIPT, db_env, ["--count", str(count)])
        elif step == Step.PREWARM:
            run_script(PREWARM_SCRIPT, os.environ)
        elif step in K6_SCRIPTS:
            run_k6(step, k6_vars)

    def run_all(db_env: dict) -> None:
        for step in steps_to_run:
            execute(step, db_env)

    if _env == "local":
        run_all(os.environ)
    elif needs_db_tunnel:
        with ssm_tunnel(Service.DB) as (host, port):
            tunnelled = {**os.environ, "DB_HOST": host, "DB_PORT": str(port), "BASTION_ID": ""}
            run_all(tunnelled)
    else:
        run_all(os.environ)

    print(f"\n✓ Pipeline complete.", file=sys.stderr)
    if Step.TOKENS in steps_to_run:
        print(f"  source {get_out_filepath(_env, OutFile.TOKENS_ENV)}", file=sys.stderr)
    if Step.IDS in steps_to_run:
        print(f"  source {get_out_filepath(_env, OutFile.IDS_ENV)}", file=sys.stderr)


if __name__ == "__main__":
    with timed("Total time:"):
        main()
