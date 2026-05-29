#!/usr/bin/env python3
"""
Runs Doctrine migrations + fixtures via Docker Compose, then queries IDs and
saves seed_result.json for use by 01_prewarm.py and 03_get_load_test_ids.py.

Usage:
  DB_PASSWORD=<secret> python scripts/00_seed_doctrine.py

Env vars:
  DB_PASSWORD  database password (required)
  CONFIG       path to YAML config (default: config/local.yaml)
"""
import os, sys, json, subprocess, pathlib
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from paths import get_out_filepath, OutFile, ROOT_DIR
from models import SeedResult
import psycopg2, psycopg2.extras
from config import load as _cfg
from utils import timed


def _php_console(args: list[str], env: dict | None = None) -> None:
    base = ["docker", "compose", "exec", "-T"]
    if env:
        for k, v in env.items():
            base += ["-e", f"{k}={v}"]
    cmd = base + ["mdg", "php", "bin/console"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT_DIR))
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(args)}")


def _db():
    cfg = _cfg()["database"]
    return psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["name"],
        user=cfg["user"],
        password=os.environ["DB_PASSWORD"],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def seed() -> SeedResult:
    with timed("doctrine:migrations:migrate"):
        _php_console(["doctrine:migrations:migrate", "--no-interaction"])

    with timed("doctrine:fixtures:load"):
        _php_console(["doctrine:fixtures:load", "--no-interaction"], env={"APP_ENV": "dev"})

    conn = _db()
    try:
        with conn.cursor() as cur:
            # topic_ids in fixture insertion order: technology, politics, sports
            cur.execute(
                "SELECT topic_id FROM topics "
                "ORDER BY CASE name WHEN 'technology' THEN 1 WHEN 'politics' THEN 2 WHEN 'sports' THEN 3 END"
            )
            topic_ids = [r["topic_id"] for r in cur.fetchall()]

            cur.execute("SELECT newsletter_id, topic_id::text, date::text FROM newsletters ORDER BY date, topic_id")
            nl_ids = {f"{r['topic_id']}|{r['date']}": r["newsletter_id"] for r in cur.fetchall()}

            cur.execute("SELECT MIN(date) FROM newsletters")
            start: date = cur.fetchone()["min"]
    finally:
        conn.close()

    return SeedResult(topic_ids=topic_ids, nl_ids=nl_ids, start=start)


def _save(result: SeedResult, env: str) -> None:
    payload = {
        "topic_ids": [str(tid) for tid in result.topic_ids],
        "nl_ids": {k: str(v) for k, v in result.nl_ids.items()},
        "start": str(result.start),
    }
    out_path = get_out_filepath(env, OutFile.SEED_RESULT)
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"  Seed result saved → {out_path}")


if __name__ == "__main__":
    _env = os.environ.get("env", "local")
    if _env != "local":
        print(
            f"ERROR: env={_env} not supported by 00_seed_doctrine.py. "
            "Run migrations via ECS task override for non-local environments.",
            file=sys.stderr,
        )
        sys.exit(1)

    with timed("Total time:"):
        try:
            result = seed()
        except Exception as e:
            print(f"✗ {e}", file=sys.stderr)
            sys.exit(1)

        _save(result, _env)
        print("  next: python scripts/01_prewarm.py", file=sys.stderr)
