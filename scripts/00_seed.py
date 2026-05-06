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
from datetime import timedelta, date
import psycopg2, psycopg2.extras, redis
from tunnel import ssm_tunnel, ssm_redis_tunnel
from config import load as _cfg
from utils import timed

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


def redis_client(host: str | None = None, port: int | None = None):
    cfg = _cfg()["redis"]
    use_ssl = cfg["ssl"]
    tunnelled = host is not None
    return redis.Redis(
        host=host or cfg["host"],
        port=port or cfg["port"],
        ssl=use_ssl,
        ssl_cert_reqs=None if tunnelled else "required",
        ssl_check_hostname=not tunnelled,
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

def seed(conn):
    if not _schema_exists(conn):
        create_schema(conn)
    else:
        print("Schema already exists, skipping.")

    start = date.today() - timedelta(days=DAYS)
    xv = psycopg2.extras.execute_values
    with conn.cursor() as cur:

        print("Truncating...")
        with timed("Truncated all tables"):
            cur.execute("""TRUNCATE interactions, newsletter_context_links, newsletter_events,
                newsletters, event_thread_memberships, news_events, threads, subscriptions, topics CASCADE""")

        with timed("Inserted topics"):
            rows = xv(cur,
                "INSERT INTO topics (name, description) VALUES %s RETURNING topic_id",
                [(t["name"], t["description"]) for t in TOPICS],
                fetch=True)
            topic_ids = [r["topic_id"] for r in rows]
            print(f"  topics: {len(topic_ids)}")

        thread_ids = {}
        thr_to_topic = {}
        with timed("Inserted threads"):
            thread_rows = [(tid, f"Thread {i+1} ({tid})") for tid in topic_ids for i in range(THREADS_PER_TOPIC)]
            rows = xv(cur,
                "INSERT INTO threads (topic_id, name) VALUES %s RETURNING thread_id, topic_id",
                thread_rows,
                fetch=True)
            for r in rows:
                thread_ids.setdefault(r["topic_id"], []).append(r["thread_id"])
                thr_to_topic[r["thread_id"]] = r["topic_id"]
            print(f"  threads: {sum(len(v) for v in thread_ids.values())}")

        all_events = []
        thread_event_map = {}
        with timed("Inserted news_events and event_thread_memberships"):
            event_rows, event_meta = [], []
            for tid, thr_ids in thread_ids.items():
                for thr_id in thr_ids:
                    for pos in range(1, EVENTS_PER_THREAD + 1):
                        ev_date = start + timedelta(days=(pos - 1) * (DAYS // EVENTS_PER_THREAD))
                        event_rows.append((f"Headline {pos} / thread {thr_id}", f"Summary of event {pos}.", ev_date, f"https://example.com/{uuid.uuid4()}"))
                        event_meta.append((thr_id, pos))

            rows = xv(cur,
                "INSERT INTO news_events (headline, summary, date, source_url) VALUES %s RETURNING event_id",
                event_rows, fetch=True, page_size=300)
            ev_id_list = [r["event_id"] for r in rows]

            membership_rows = []
            prev_by_thread = {}
            for idx, (thr_id, pos) in enumerate(event_meta):
                ev_id = ev_id_list[idx]
                all_events.append((ev_id, thr_to_topic[thr_id], thr_id))
                thread_event_map.setdefault(thr_id, []).append(ev_id)
                membership_rows.append((ev_id, thr_id, pos, prev_by_thread.get(thr_id)))
                prev_by_thread[thr_id] = ev_id

            xv(cur,
                "INSERT INTO event_thread_memberships (event_id, thread_id, position, previous_event_id) VALUES %s",
                membership_rows, page_size=300)
            print(f"  news_events: {len(all_events)}")

        nl_ids = {}
        with timed("Inserted newsletters and newsletter_events"):
            nl_data = [(tid, start + timedelta(days=day), f"Newsletter {start + timedelta(days=day)} — {tid}", f"Narrative for {tid} on {start + timedelta(days=day)}.")
                       for day in range(DAYS) for tid in topic_ids]
            rows = xv(cur,
                "INSERT INTO newsletters (topic_id, date, title, narrative) VALUES %s RETURNING newsletter_id",
                nl_data, fetch=True, page_size=100)

            nl_event_rows = []
            for idx, (tid, nl_date, _, _) in enumerate(nl_data):
                nl_id = rows[idx]["newsletter_id"]
                nl_ids[(str(tid), str(nl_date))] = nl_id
                chosen = [(eid, thr) for eid, top, thr in all_events if top == tid][:EVENTS_PER_NEWSLETTER]
                nl_event_rows.extend((nl_id, eid, thr_id, pos) for pos, (eid, thr_id) in enumerate(chosen, 1))

            xv(cur,
                "INSERT INTO newsletter_events (newsletter_id, event_id, thread_id, position) VALUES %s",
                nl_event_rows, page_size=500)
            print(f"  newsletters: {len(nl_ids)}")

        nl_list = list(nl_ids.values())
        with timed("Inserted newsletter_context_links"):
            ctx_rows = [(nl_id, linked, f"Background context (link {pos})", pos)
                        for i, nl_id in enumerate(nl_list) if i >= 2
                        for pos, linked in enumerate(nl_list[max(0, i-2):i], 1)]
            xv(cur,
                "INSERT INTO newsletter_context_links (newsletter_id, linked_newsletter_id, reason, position) VALUES %s",
                ctx_rows, page_size=500)
            print(f"  context_links: inserted")

        with timed("Inserted subscriptions"):
            sub_rows = [(f"mock-user-{u:04d}", tid) for u in range(MOCK_USERS) for tid in topic_ids[:2]]
            xv(cur,
                "INSERT INTO subscriptions (user_id, topic_id) VALUES %s ON CONFLICT DO NOTHING",
                sub_rows, page_size=1000)
            print(f"  subscriptions: {MOCK_USERS} users × 2 topics")

        ev_ids = [e for e, _, _ in all_events[:100]]
        types = ["view", "click", "deep_dive"]
        with timed("Inserted interactions"):
            interaction_rows = [(f"mock-user-{i % MOCK_USERS:04d}", ev_ids[i % len(ev_ids)], types[i % 3]) for i in range(10000)]
            xv(cur,
                "INSERT INTO interactions (user_id, event_id, type) VALUES %s",
                interaction_rows, page_size=1000)
            print(f"  interactions: 10000")

    conn.commit()
    return topic_ids, nl_ids, start


def prewarm_redis(rc, topic_ids, nl_ids, start):
    print("Pre-warming Redis...")
    with timed("Flushed redis"):
        rc.flushall()
    latest_date = str(start + timedelta(days=DAYS - 1))
    with timed("Pre-warmed Redis"):
        with rc.pipeline(transaction=False) as pipe:
            for tid in topic_ids:
                nl_id = nl_ids.get((str(tid), latest_date))
                if nl_id:
                    pipe.set(f"newsletter:{nl_id}", json.dumps({"newsletter_id": str(nl_id), "date": latest_date}), ex=REDIS_TTL)
            pipe.execute()
    print("Redis pre-warmed.\n✓ Seed complete")


def _run_db(conn):
    try:
        return seed(conn)
    except Exception as e:
        conn.rollback()
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


def _run_redis(rc, topic_ids, nl_ids, start):
    try:
        prewarm_redis(rc, topic_ids, nl_ids, start)
    except Exception as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        rc.close()


if __name__ == "__main__":
    _env = os.environ.get("env", "local")
    with timed("Total time:"):
        if _env == "local":
            result = _run_db(db())
        else:
            with ssm_tunnel() as (db_host, db_port):
                result = _run_db(db(db_host, db_port))

        if result is None:
            print("✗ Seeding failed, cannot pre-warm Redis.", file=sys.stderr)
            sys.exit(1)

        topic_ids, nl_ids, start = result

        if _env == "local":
            _run_redis(redis_client(), topic_ids, nl_ids, start)
        else:
            with ssm_redis_tunnel() as (r_host, r_port):
                _run_redis(redis_client(r_host, r_port), topic_ids, nl_ids, start)
