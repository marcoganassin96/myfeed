#!/usr/bin/env python3
"""
Queries live DB for newsletter and event IDs for k6 load tests.

Outputs:
  scripts/out/01_ids.env  — export NEWSLETTER_IDS=... and EVENT_IDS=...

Usage:
  CONFIG=config/dev.yaml DB_PASSWORD=<secret> python scripts/02_get_load_test_ids.py [--count N]

Env vars:
  CONFIG       path to YAML config file (default: config/local.yaml)
  DB_PASSWORD  database password (required)
  BASTION_ID   EC2 instance ID; if set, opens SSM tunnel localhost:15433 → DB_HOST:5432
"""
import argparse
import os
import pathlib
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from paths import IDS_ENV
from tunnel import ssm_tunnel
from config import load as _cfg
from utils import timed


def main(db_host: str, db_port: int, count: int):
    cfg = _cfg()["database"]
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=cfg["name"],
        user=cfg["user"],
        password=os.environ["DB_PASSWORD"],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    try:
        with timed("Fetched IDs from DB"):
            cur = conn.cursor()
            cur.execute("SELECT newsletter_id FROM newsletters LIMIT %s", (count,))
            newsletter_ids = ",".join(str(r["newsletter_id"]) for r in cur.fetchall())
            cur.execute("SELECT event_id FROM news_events LIMIT %s", (count,))
            event_ids = ",".join(str(r["event_id"]) for r in cur.fetchall())
    finally:
        conn.close()

    IDS_ENV.parent.mkdir(exist_ok=True)
    IDS_ENV.write_text(
        f"export NEWSLETTER_IDS={newsletter_ids}\n"
        f"export EVENT_IDS={event_ids}\n"
    )
    print(f"✓ {count} newsletter IDs, {count} event IDs → {IDS_ENV}")
    print(f"  next: source {IDS_ENV}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20)
    args = parser.parse_args()

    _env = os.environ.get("env", "local")
    with timed("Total time:"):
        if _env == "local":
            _db = _cfg()["database"]
            main(_db["host"], _db["port"], args.count)
        else:
            with ssm_tunnel() as (host, port):
                main(host, port, args.count)
