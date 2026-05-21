#!/usr/bin/env python3
"""
k6 load-test runner. Reads tokens and IDs from scripts/out/, then runs
scenarios in ascending order of stress.

Usage (standalone):
  CONFIG=config/dev.yaml python scripts/run_load_tests.py [--scenario STEP] [--continue-on-failure]

Usage (imported by pipeline.py):
  from run_load_tests import load_k6_vars, run_k6, preflight_k6

Scenarios (in order):
  smoke   — 1 VU · sanity check
  uncached — 200 VUs · p99<300ms
  cached  — 500 VUs · p99<50ms
  sse     — 50 VUs · first chunk<500ms
  mixed   — 1000 VUs · p95<200ms
  stress  — spike 0→1000 VUs · errors<1%

Env vars:
  CONFIG          path to YAML config file (default: config/local.yaml)
  COGNITO_TOKEN   override token from scripts/out/
  NEWSLETTER_IDS  override IDs from scripts/out/
  EVENT_IDS       override IDs from scripts/out/
  API_URL         override API URL from config
"""
import argparse
import os
import pathlib
import shutil
import subprocess
import sys

SCRIPTS = pathlib.Path(__file__).parent
sys.path.insert(0, str(SCRIPTS))

from paths import ROOT_DIR, get_out_filepath, OutFile  # noqa: E402
from config import load as _cfg                        # noqa: E402
from steps import Step, K6_SCRIPTS                    # noqa: E402
from utils import timed, die                           # noqa: E402

LOAD_TESTS = ROOT_DIR / "load_tests" / "newsletter"


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


def load_k6_vars(_env: str, runtime: str = "lambda") -> dict[str, str]:
    tokens_env = parse_env_file(get_out_filepath(_env, OutFile.TOKENS_ENV))
    ids_env    = parse_env_file(get_out_filepath(_env, OutFile.IDS_ENV))
    token = os.environ.get("COGNITO_TOKEN") or tokens_env.get("COGNITO_TOKEN", "")
    if not token:
        tokens_txt = get_out_filepath(_env, OutFile.TOKENS_TXT)
        if tokens_txt.exists():
            lines = [ln.strip() for ln in tokens_txt.read_text().splitlines() if ln.strip()]
            token = lines[0] if lines else ""
    cfg = _cfg()
    if runtime == "fargate":
        cfg_url = cfg.get("fargate", {}).get("alb_url") or cfg["api"]["url"]
    else:
        cfg_url = cfg["api"]["url"]
    return {
        "API_URL":        os.environ.get("API_URL") or cfg_url,
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


def preflight_k6(steps: list[Step], _env: str, runtime: str = "lambda") -> dict[str, str]:
    """Load and validate k6 vars if any k6 step is scheduled. Returns {} otherwise."""
    if not any(s in K6_SCRIPTS for s in steps):
        return {}
    k6_vars = load_k6_vars(_env, runtime=runtime)
    will_generate = Step.TOKENS in steps or Step.IDS in steps
    if not will_generate:
        missing = [k for k, v in k6_vars.items() if not v]
        if missing:
            die(f"Missing k6 vars: {', '.join(missing)} — run seed/tokens/ids steps first")
    print(f"\nAPI: {k6_vars['API_URL']}", file=sys.stderr)
    if not will_generate:
        print(f"Token: {k6_vars['COGNITO_TOKEN'][:20]}...", file=sys.stderr)
        print(
            f"Newsletter IDs: {len(k6_vars['NEWSLETTER_IDS'].split(','))}"
            f"  Event IDs: {len(k6_vars['EVENT_IDS'].split(','))}",
            file=sys.stderr,
        )
    return k6_vars


def _run_standalone(scenario: str | None, continue_on_failure: bool, _env: str) -> None:
    steps = [Step(s) for s in K6_SCRIPTS] if scenario is None else [Step(scenario)]
    k6_vars = preflight_k6(steps, _env)
    results: list[tuple[Step, bool]] = []
    for step in steps:
        try:
            run_k6(step, k6_vars)
            results.append((step, True))
        except SystemExit:
            results.append((step, False))
            if not continue_on_failure:
                break

    print(f"\n{'='*60}", file=sys.stderr)
    print("  RESULTS", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    all_passed = True
    for step, passed in results:
        icon = "✓" if passed else "✗"
        print(f"  {icon}  {step}", file=sys.stderr)
        if not passed:
            all_passed = False
    skipped = len(steps) - len(results)
    if skipped:
        print(f"\n  (skipped {skipped} scenario(s) due to failure)", file=sys.stderr)
    print(file=sys.stderr)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--scenario",
        choices=[s for s in K6_SCRIPTS],
        metavar="STEP",
        help=f"Run one scenario only. Choices: {', '.join(K6_SCRIPTS)}",
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Keep running remaining scenarios after a failure",
    )
    args = parser.parse_args()
    _env = os.environ.get("env", "local")
    with timed("Total time:"):
        _run_standalone(args.scenario, args.continue_on_failure, _env)
