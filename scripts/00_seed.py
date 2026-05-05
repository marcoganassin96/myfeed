#!/usr/bin/env python3
"""
Truncates all tables, inserts mock data, and pre-warms Redis.

Usage:
  CONFIG=config/dev.yaml DB_PASSWORD=<secret> python scripts/00_seed.py

Env vars:
  CONFIG       path to YAML config file (default: config/local.yaml)
  DB_PASSWORD  database password (required)
"""
import os, sys, json, uuid, pathlib
from datetime import date, timedelta
import psycopg2, psycopg2.extras, redis
from tunnel import ssm_tunnel
from config import load as _cfg

_MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent / "migrations"
_INITIAL_SCHEMA = "001_initial_schema.sql"

TOPICS = [
    {"name": "technology", "description": "AI, software, and hardware news"},
    {"name": "politics",   "description": "Global political developments"},
    {"name": "sports",     "description": "Sports events and results"},
]
THREADS_PER_TOPIC = 5
EVENTS_PER_THREAD = 20
EVENTS_PER_NEWSLETTER = 5
DAYS = 30
MOCK_USERS = 1000
REDIS_TTL = 3600


def db(host: str | None = None, port: int | None = None):
    cfg = _cfg()["database"]
    return psycopg2.connect(
        host=host or cfg["host"],
        port=port or cfg["port"],
        dbname=cfg["name"],
        user=cfg["user"],
        password=os.environ["DB_PASSWORD"],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def redis_client():
    cfg = _cfg()["redis"]
    return redis.Redis(
        host=cfg["host"],
        port=cfg["port"],
        ssl=cfg["ssl"],
        decode_responses=True,
    )


def _schema_exists(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='topics'"
        )
        return cur.fetchone() is not None


def create_schema(conn, migration: str = _INITIAL_SCHEMA):
    sql = (_MIGRATIONS_DIR / migration).read_text()
    sql = sql.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ")
    sql = sql.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"Schema applied ({migration}).")

def seed(conn, rc):
    start = date.today() - timedelta(days=DAYS)
    with conn.cursor() as cur:
        print("Truncating...")
        cur.execute("""TRUNCATE interactions, newsletter_context_links, newsletter_events,
            newsletters, event_thread_memberships, news_events, threads, subscriptions, topics CASCADE""")

        topic_ids = []
        for t in TOPICS:
            cur.execute("INSERT INTO topics (name, description) VALUES (%s,%s) RETURNING topic_id", (t["name"], t["description"]))
            topic_ids.append(cur.fetchone()["topic_id"])
        print(f"  topics: {len(topic_ids)}")

        thread_ids = {}
        for tid in topic_ids:
            thread_ids[tid] = []
            for i in range(THREADS_PER_TOPIC):
                cur.execute("INSERT INTO threads (topic_id, name) VALUES (%s,%s) RETURNING thread_id",
                            (tid, f"Thread {i+1} ({tid})"))
                thread_ids[tid].append(cur.fetchone()["thread_id"])
        print(f"  threads: {sum(len(v) for v in thread_ids.values())}")

        all_events = []
        thread_event_map = {}
        for tid, thr_ids in thread_ids.items():
            for thr_id in thr_ids:
                thread_event_map[thr_id] = []
                prev = None
                for pos in range(1, EVENTS_PER_THREAD + 1):
                    ev_date = start + timedelta(days=(pos - 1) * (DAYS // EVENTS_PER_THREAD))
                    cur.execute(
                        "INSERT INTO news_events (headline, summary, date, source_url) VALUES (%s,%s,%s,%s) RETURNING event_id",
                        (f"Headline {pos} / thread {thr_id}", f"Summary of event {pos}.", ev_date,
                         f"https://example.com/{uuid.uuid4()}"))
                    ev_id = cur.fetchone()["event_id"]
                    cur.execute(
                        "INSERT INTO event_thread_memberships (event_id,thread_id,position,previous_event_id) VALUES (%s,%s,%s,%s)",
                        (ev_id, thr_id, pos, prev))
                    thread_event_map[thr_id].append(ev_id)
                    all_events.append((ev_id, tid, thr_id))
                    prev = ev_id
        print(f"  news_events: {len(all_events)}")

        nl_ids = {}
        for day in range(DAYS):
            nl_date = start + timedelta(days=day)
            for tid in topic_ids:
                cur.execute(
                    "INSERT INTO newsletters (topic_id,date,title,narrative) VALUES (%s,%s,%s,%s) RETURNING newsletter_id",
                    (tid, nl_date, f"Newsletter {nl_date} — {tid}", f"Narrative for {tid} on {nl_date}."))
                nl_id = cur.fetchone()["newsletter_id"]
                nl_ids[(str(tid), str(nl_date))] = nl_id
                chosen = [(eid, thr) for eid, top, thr in all_events if top == tid][:EVENTS_PER_NEWSLETTER]
                for pos, (eid, thr_id) in enumerate(chosen, 1):
                    cur.execute("INSERT INTO newsletter_events (newsletter_id,event_id,thread_id,position) VALUES (%s,%s,%s,%s)",
                                (nl_id, eid, thr_id, pos))
        print(f"  newsletters: {len(nl_ids)}")

        nl_list = list(nl_ids.values())
        for i, nl_id in enumerate(nl_list):
            if i < 2: continue
            for pos, linked in enumerate(nl_list[max(0,i-2):i], 1):
                cur.execute("INSERT INTO newsletter_context_links (newsletter_id,linked_newsletter_id,reason,position) VALUES (%s,%s,%s,%s)",
                            (nl_id, linked, f"Background context (link {pos})", pos))
        print(f"  context_links: inserted")

        for u in range(MOCK_USERS):
            uid = f"mock-user-{u:04d}"
            for tid in topic_ids[:2]:
                cur.execute("INSERT INTO subscriptions (user_id,topic_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (uid, tid))
        print(f"  subscriptions: {MOCK_USERS} users × 2 topics")

        ev_ids = [e for e, _, _ in all_events[:100]]
        types = ["view", "click", "deep_dive"]
        for i in range(10000):
            cur.execute("INSERT INTO interactions (user_id,event_id,type) VALUES (%s,%s,%s)",
                        (f"mock-user-{i % MOCK_USERS:04d}", ev_ids[i % len(ev_ids)], types[i % 3]))
        print(f"  interactions: 10000")

    conn.commit()

    print("Pre-warming Redis...")
    rc.flushall()
    latest_date = str(start + timedelta(days=DAYS - 1))
    for tid in topic_ids:
        nl_id = nl_ids.get((str(tid), latest_date))
        if nl_id:
            rc.setex(f"newsletter:{nl_id}", REDIS_TTL, json.dumps({"newsletter_id": str(nl_id), "date": latest_date}))
    print("Redis pre-warmed.\n✓ Seed complete")

def _run(conn, rc):
    try:
        if not _schema_exists(conn):
            create_schema(conn)
        else:
            print("Schema already exists, skipping.")
        seed(conn, rc)
    except Exception as e:
        conn.rollback()
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    _env = os.environ.get("env", "local")
    if _env == "local":
        _run(db(), redis_client())
    else:
        with ssm_tunnel() as (host, port):
            _run(db(host, port), redis_client())
