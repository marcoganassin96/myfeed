#!/usr/bin/env python3
"""
Progressive k6 load test runner. Reads tokens and IDs from scripts/out/,
then runs all five scenarios in ascending order of stress.

Usage:
  CONFIG=config/dev.yaml python scripts/04_run_load_tests.py [--scenario NAME] [--continue-on-failure]

Scenarios (run in this order by default):
  newsletter_cached    — 500 VUs, p99 < 50ms
  newsletter_cold      — 200 VUs, p99 < 300ms
  deep_dive_sse        — 50 VUs, first chunk < 500ms
  mixed_realistic      — 1000 VUs, p95 < 200ms
  cold_start_stress    — spike 0→1000 VUs, errors < 1%

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

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from paths import ROOT_DIR, get_out_filepath, OutFile
from config import load as _cfg
from utils import timed

LOAD_TESTS = ROOT_DIR / "load_tests"

SCENARIOS = [
    ("newsletter_cached",  "newsletter_cached.js",  "500 VUs · p99<50ms"),
    ("newsletter_cold",    "newsletter_cold.js",     "200 VUs · p99<300ms"),
    ("deep_dive_sse",      "deep_dive_sse.js",       "50 VUs · SSE first-chunk<500ms"),
    ("mixed_realistic",    "mixed_realistic.js",     "1000 VUs · p95<200ms"),
    ("cold_start_stress",  "cold_start_stress.js",   "spike 0→1000 VUs · errors<1%"),
]


def parse_env_file(path: pathlib.Path) -> dict[str, str]:
    result = {}
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


def load_vars() -> dict[str, str]:
    _env = os.environ.get("env", "local")
    tokens_env = parse_env_file(get_out_filepath(_env, OutFile.TOKENS_ENV))
    ids_env = parse_env_file(get_out_filepath(_env, OutFile.IDS_ENV))

    token = os.environ.get("COGNITO_TOKEN") or tokens_env.get("COGNITO_TOKEN", "")
    if not token:
        tokens_txt = get_out_filepath(_env, OutFile.TOKENS_TXT)
        if tokens_txt.exists():
            lines = [l.strip() for l in tokens_txt.read_text().splitlines() if l.strip()]
            token = lines[0] if lines else ""

    return {
        "API_URL": os.environ.get("API_URL") or _cfg()["api"]["url"],
        "COGNITO_TOKEN": os.environ.get("COGNITO_TOKEN") or token,
        "NEWSLETTER_IDS": os.environ.get("NEWSLETTER_IDS") or ids_env.get("NEWSLETTER_IDS", ""),
        "EVENT_IDS": os.environ.get("EVENT_IDS") or ids_env.get("EVENT_IDS", ""),
    }


def k6_executable() -> str:
    path = shutil.which("k6")
    if path is None:
        print("✗ k6 not found in PATH. Install from https://k6.io/docs/getting-started/installation/", file=sys.stderr)
        sys.exit(1)
    return path


def run_scenario(name: str, script: str, description: str, vars: dict[str, str]) -> bool:
    print(f"\n{'='*60}")
    print(f"  {name}  —  {description}")
    print(f"{'='*60}")

    cmd = [
        k6_executable(), "run",
        "-e", f"API_URL={vars['API_URL']}",
        "-e", f"COGNITO_TOKEN={vars['COGNITO_TOKEN']}",
        "-e", f"NEWSLETTER_IDS={vars['NEWSLETTER_IDS']}",
        "-e", f"EVENT_IDS={vars['EVENT_IDS']}",
        str(LOAD_TESTS / script),
    ]

    with timed(name):
        result = subprocess.run(cmd)

    passed = result.returncode == 0
    status = "✓ PASSED" if passed else "✗ FAILED"
    print(f"\n  {status}: {name}")
    return passed


def main():
    parser = argparse.ArgumentParser(description="Progressive k6 load test runner")
    parser.add_argument(
        "--scenario",
        choices=[s[0] for s in SCENARIOS],
        help="Run a single scenario instead of all five",
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Keep running remaining scenarios even if one fails",
    )
    args = parser.parse_args()

    vars = load_vars()

    missing = [k for k, v in vars.items() if not v]
    if missing:
        print(f"✗ Missing required values: {', '.join(missing)}", file=sys.stderr)
        print(f"  Run pipeline.py first, or set env vars directly.", file=sys.stderr)
        sys.exit(1)

    scenarios = SCENARIOS if not args.scenario else [s for s in SCENARIOS if s[0] == args.scenario]

    print(f"\nAPI: {vars['API_URL']}")
    print(f"Token: {vars['COGNITO_TOKEN'][:30]}...")
    print(f"Newsletter IDs: {len(vars['NEWSLETTER_IDS'].split(','))} loaded")
    print(f"Event IDs: {len(vars['EVENT_IDS'].split(','))} loaded")
    print(f"\nRunning {len(scenarios)} scenario(s)...")

    results: list[tuple[str, bool]] = []
    for name, script, description in scenarios:
        passed = run_scenario(name, script, description, vars)
        results.append((name, passed))
        if not passed and not args.continue_on_failure:
            print(f"\n✗ Stopping after first failure. Use --continue-on-failure to run all.", file=sys.stderr)
            break

    print(f"\n{'='*60}")
    print("  RESULTS")
    print(f"{'='*60}")
    all_passed = True
    for name, passed in results:
        icon = "✓" if passed else "✗"
        print(f"  {icon}  {name}")
        if not passed:
            all_passed = False

    skipped = len(scenarios) - len(results)
    if skipped:
        print(f"\n  (skipped {skipped} scenario(s) due to failure)")

    print()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    with timed("Total time:"):
        main()
