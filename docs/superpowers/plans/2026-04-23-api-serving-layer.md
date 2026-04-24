# API / Serving Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and load-test the AWS Lambda + API Gateway serving layer with mocked PostgreSQL + Redis data, capable of sustaining 1,000 req/s at p95 < 200ms.

**Architecture:** Four Python Lambda functions behind API Gateway with Cognito auth. ElastiCache Redis caches newsletter reads (TTL 1h). Aurora Serverless v2 PostgreSQL stores all data, accessed via RDS Proxy. The deep-dive endpoint uses Lambda Response Streaming to return SSE chunks. All data is seeded via `seed.py`; no real NLP/LLM pipeline exists in this phase.

**Tech Stack:** Python 3.12, AWS SAM, psycopg2-binary, redis-py, pytest, pytest-mock, k6, Docker (local dev)

---

## Pre-requisites (before Task 11 deploy)

The SAM template accepts these as parameters — provision them separately first:
- VPC with private subnets
- Aurora Serverless v2 cluster + RDS Proxy endpoint
- ElastiCache Serverless (Redis) cluster
- Note the RDS Proxy endpoint, Redis endpoint, VPC ID, and subnet IDs

---

## File Map

| File | Responsibility |
|---|---|
| `src/db.py` | Aurora connection via psycopg2 + RDS Proxy; module-level connection reuse |
| `src/cache.py` | Redis client; `cache_get` / `cache_set` with JSON serialisation |
| `src/response.py` | HTTP response builders: `ok`, `created`, `no_content`, `bad_request`, `not_found`, `server_error` |
| `src/handlers/newsletters.py` | `GET /newsletters`, `GET /newsletters/{newsletter_id}` |
| `src/handlers/subscriptions.py` | `GET /subscriptions`, `POST /subscriptions`, `DELETE /subscriptions/{topic_id}` |
| `src/handlers/interactions.py` | `POST /interactions` |
| `src/handlers/deep_dive.py` | `POST /deep-dive/{event_id}` — SSE streaming |
| `migrations/001_initial_schema.sql` | All `CREATE TABLE` + `CREATE INDEX` statements |
| `scripts/seed.py` | Truncate → insert mock data → pre-warm Redis. Idempotent. |
| `scripts/create_test_tokens.py` | Create 100 Cognito test users and print Bearer tokens |
| `load_tests/config.js` | Shared k6 constants (base URL, headers, ID lists) |
| `load_tests/newsletter_cached.js` | k6: 500 VUs, cached newsletter reads, p99 < 50ms |
| `load_tests/newsletter_cold.js` | k6: 200 VUs, cache-miss reads, p99 < 300ms |
| `load_tests/mixed_realistic.js` | k6: 1,000 VUs, 60/30/10 split, p95 < 200ms |
| `load_tests/deep_dive_sse.js` | k6: 50 VUs, SSE streaming, first chunk < 500ms |
| `load_tests/cold_start_stress.js` | k6: spike 0→1,000 VUs in 10s, error rate < 1% |
| `infra/template.yaml` | SAM: Lambda, API Gateway, Cognito |
| `docker-compose.yml` | Local PostgreSQL + Redis for tests |
| `tests/conftest.py` | pytest fixtures: `mock_db`, `mock_cache`, `api_event` |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `docker-compose.yml`
- Create: `src/__init__.py`, `src/handlers/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Create `requirements.txt`**

```
psycopg2-binary==2.9.9
redis==5.0.4
```

- [ ] **Step 2: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest==8.2.0
pytest-mock==3.14.0
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.env
venv/
.aws-sam/
*.egg-info/
.superpowers/
```

- [ ] **Step 4: Create `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: newsletter
      POSTGRES_USER: newsletter
      POSTGRES_PASSWORD: newsletter
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./migrations:/docker-entrypoint-initdb.d

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  postgres_data:
```

- [ ] **Step 5: Create directory structure and init files**

```bash
mkdir -p src/handlers tests scripts load_tests migrations infra
touch src/__init__.py src/handlers/__init__.py tests/__init__.py
```

- [ ] **Step 6: Install dependencies**

```bash
pip install -r requirements-dev.txt
```

Expected: `Successfully installed psycopg2-binary-2.9.9 redis-5.0.4 pytest-8.2.0 pytest-mock-3.14.0`

- [ ] **Step 7: Commit**

```bash
git add requirements.txt requirements-dev.txt .gitignore docker-compose.yml src/ tests/ scripts/ load_tests/ migrations/ infra/
git commit -m "chore: project scaffolding and dependencies"
```

---

### Task 2: Database Schema

**Files:**
- Create: `migrations/001_initial_schema.sql`

- [ ] **Step 1: Write the schema**

```sql
-- migrations/001_initial_schema.sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE topics (
    topic_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(100) UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE threads (
    thread_id  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id   UUID         NOT NULL REFERENCES topics ON DELETE CASCADE,
    name       VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_threads_topic_id ON threads (topic_id);

CREATE TABLE news_events (
    event_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    headline   VARCHAR(300) NOT NULL,
    summary    TEXT         NOT NULL,
    date       DATE         NOT NULL,
    source_url TEXT
);

CREATE TABLE event_thread_memberships (
    event_id          UUID NOT NULL REFERENCES news_events ON DELETE CASCADE,
    thread_id         UUID NOT NULL REFERENCES threads ON DELETE CASCADE,
    position          INT  NOT NULL,
    previous_event_id UUID REFERENCES news_events ON DELETE SET NULL,
    PRIMARY KEY (event_id, thread_id)
);
CREATE INDEX idx_etm_thread_position ON event_thread_memberships (thread_id, position);

CREATE TABLE newsletters (
    newsletter_id UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id      UUID         NOT NULL REFERENCES topics ON DELETE CASCADE,
    date          DATE         NOT NULL,
    title         VARCHAR(200) NOT NULL,
    narrative     TEXT         NOT NULL,
    UNIQUE (topic_id, date)
);
CREATE INDEX idx_newsletters_topic_date ON newsletters (topic_id, date DESC);

CREATE TABLE newsletter_events (
    newsletter_id UUID NOT NULL REFERENCES newsletters ON DELETE CASCADE,
    event_id      UUID NOT NULL REFERENCES news_events ON DELETE CASCADE,
    thread_id     UUID NOT NULL REFERENCES threads ON DELETE CASCADE,
    position      INT  NOT NULL,
    PRIMARY KEY (newsletter_id, event_id)
);
CREATE INDEX idx_newsletter_events_nl_pos ON newsletter_events (newsletter_id, position);

CREATE TABLE newsletter_context_links (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    newsletter_id        UUID NOT NULL REFERENCES newsletters ON DELETE CASCADE,
    linked_newsletter_id UUID NOT NULL REFERENCES newsletters ON DELETE CASCADE,
    reason               TEXT NOT NULL,
    position             INT  NOT NULL
);
CREATE INDEX idx_ncl_newsletter_id ON newsletter_context_links (newsletter_id);

CREATE TABLE subscriptions (
    user_id       VARCHAR     NOT NULL,
    topic_id      UUID        NOT NULL REFERENCES topics ON DELETE CASCADE,
    subscribed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, topic_id)
);
CREATE INDEX idx_subscriptions_user_id ON subscriptions (user_id);

CREATE TABLE interactions (
    interaction_id UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        VARCHAR     NOT NULL,
    event_id       UUID        NOT NULL REFERENCES news_events ON DELETE CASCADE,
    type           VARCHAR(20) NOT NULL CHECK (type IN ('view', 'click', 'deep_dive')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_interactions_user_date ON interactions (user_id, created_at DESC);
```

- [ ] **Step 2: Start local services and apply schema**

```bash
docker compose up -d
sleep 3
docker compose exec postgres psql -U newsletter -d newsletter -f /docker-entrypoint-initdb.d/001_initial_schema.sql
```

Expected: `CREATE TABLE` printed 9 times, `CREATE INDEX` printed 7 times.

- [ ] **Step 3: Verify tables exist**

```bash
docker compose exec postgres psql -U newsletter -d newsletter -c "\dt"
```

Expected: 9 tables listed.

- [ ] **Step 4: Commit**

```bash
git add migrations/001_initial_schema.sql
git commit -m "feat: PostgreSQL schema — 9 tables with indexes and foreign keys"
```

---

### Task 3: DB Connection Module

**Files:**
- Create: `src/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_db.py
import os
import pytest
from unittest.mock import MagicMock
import psycopg2.extras


def test_get_connection_creates_connection_with_env_vars(mocker):
    mock_connect = mocker.patch("psycopg2.connect")
    mock_conn = MagicMock()
    mock_conn.closed = 0
    mock_connect.return_value = mock_conn

    os.environ.update({
        "DB_HOST": "localhost", "DB_PORT": "5432",
        "DB_NAME": "newsletter", "DB_USER": "newsletter", "DB_PASSWORD": "newsletter",
    })

    import src.db as db_module
    db_module._connection = None

    conn = db_module.get_connection()

    mock_connect.assert_called_once_with(
        host="localhost", port=5432, dbname="newsletter",
        user="newsletter", password="newsletter",
        connect_timeout=5, cursor_factory=mocker.ANY,
    )
    assert conn is mock_conn


def test_get_connection_reuses_open_connection(mocker):
    mock_connect = mocker.patch("psycopg2.connect")
    existing = MagicMock()
    existing.closed = 0

    import src.db as db_module
    db_module._connection = existing

    assert db_module.get_connection() is existing
    mock_connect.assert_not_called()


def test_get_connection_reconnects_when_closed(mocker):
    new_conn = MagicMock()
    new_conn.closed = 0
    mocker.patch("psycopg2.connect", return_value=new_conn)

    closed = MagicMock()
    closed.closed = 1

    import src.db as db_module
    db_module._connection = closed

    assert db_module.get_connection() is new_conn
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.db'`

- [ ] **Step 3: Implement `src/db.py`**

```python
# src/db.py
import os
import psycopg2
import psycopg2.extras

_connection = None


def get_connection():
    global _connection
    if _connection is None or _connection.closed:
        _connection = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", "5432")),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            connect_timeout=5,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return _connection
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_db.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/db.py tests/test_db.py
git commit -m "feat: Aurora connection module with connection reuse"
```

---

### Task 4: Redis Cache Module

**Files:**
- Create: `src/cache.py`
- Create: `tests/test_cache.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cache.py
import os
import json
from unittest.mock import MagicMock


def test_get_client_creates_redis_client(mocker):
    mock_class = mocker.patch("redis.Redis")
    mock_client = MagicMock()
    mock_class.return_value = mock_client

    os.environ.update({"REDIS_HOST": "localhost", "REDIS_PORT": "6379"})

    import src.cache as cache_module
    cache_module._client = None

    client = cache_module.get_client()
    mock_class.assert_called_once_with(
        host="localhost", port=6379, ssl=False, decode_responses=True,
    )
    assert client is mock_client


def test_cache_get_returns_none_on_miss(mocker):
    mock_client = MagicMock()
    mock_client.get.return_value = None
    mocker.patch("src.cache.get_client", return_value=mock_client)

    from src.cache import cache_get
    assert cache_get("missing") is None
    mock_client.get.assert_called_once_with("missing")


def test_cache_get_parses_json_on_hit(mocker):
    payload = {"newsletter_id": "abc", "title": "Tech"}
    mock_client = MagicMock()
    mock_client.get.return_value = json.dumps(payload)
    mocker.patch("src.cache.get_client", return_value=mock_client)

    from src.cache import cache_get
    assert cache_get("newsletter:abc") == payload


def test_cache_set_serialises_with_ttl(mocker):
    mock_client = MagicMock()
    mocker.patch("src.cache.get_client", return_value=mock_client)

    from src.cache import cache_set
    data = {"title": "Tech"}
    cache_set("newsletter:abc", data, ttl=3600)
    mock_client.setex.assert_called_once_with(
        "newsletter:abc", 3600, json.dumps(data, default=str)
    )
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_cache.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.cache'`

- [ ] **Step 3: Implement `src/cache.py`**

```python
# src/cache.py
import os
import json
import redis

_client = None


def get_client():
    global _client
    if _client is None:
        _client = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=int(os.environ.get("REDIS_PORT", "6379")),
            ssl=os.environ.get("REDIS_SSL", "false").lower() == "true",
            decode_responses=True,
        )
    return _client


def cache_get(key: str):
    raw = get_client().get(key)
    return None if raw is None else json.loads(raw)


def cache_set(key: str, value, ttl: int = 3600):
    get_client().setex(key, ttl, json.dumps(value, default=str))
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_cache.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/cache.py tests/test_cache.py
git commit -m "feat: Redis cache module with cache_get/cache_set"
```

---

### Task 5: HTTP Response Helpers

**Files:**
- Create: `src/response.py`
- Create: `tests/test_response.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_response.py
import json
from src.response import ok, created, no_content, bad_request, not_found, server_error


def test_ok_returns_200_with_json_body():
    resp = ok({"id": "123"})
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"]) == {"id": "123"}
    assert resp["headers"]["Content-Type"] == "application/json"


def test_created_returns_201():
    assert created({"id": "abc"})["statusCode"] == 201


def test_no_content_returns_204_empty_body():
    resp = no_content()
    assert resp["statusCode"] == 204
    assert resp["body"] == ""


def test_bad_request_returns_400_with_message():
    resp = bad_request("topic_id is required")
    assert resp["statusCode"] == 400
    assert json.loads(resp["body"]) == {"error": "topic_id is required"}


def test_not_found_returns_404():
    resp = not_found("Newsletter not found")
    assert resp["statusCode"] == 404
    assert json.loads(resp["body"])["error"] == "Newsletter not found"


def test_server_error_returns_500():
    resp = server_error()
    assert resp["statusCode"] == 500
    assert "error" in json.loads(resp["body"])
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_response.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.response'`

- [ ] **Step 3: Implement `src/response.py`**

```python
# src/response.py
import json

_JSON = {"Content-Type": "application/json"}


def ok(body):
    return {"statusCode": 200, "headers": _JSON, "body": json.dumps(body, default=str)}

def created(body):
    return {"statusCode": 201, "headers": _JSON, "body": json.dumps(body, default=str)}

def no_content():
    return {"statusCode": 204, "headers": {}, "body": ""}

def bad_request(message: str):
    return {"statusCode": 400, "headers": _JSON, "body": json.dumps({"error": message})}

def not_found(message: str = "Not found"):
    return {"statusCode": 404, "headers": _JSON, "body": json.dumps({"error": message})}

def server_error(message: str = "Internal server error"):
    return {"statusCode": 500, "headers": _JSON, "body": json.dumps({"error": message})}
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_response.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/response.py tests/test_response.py
git commit -m "feat: HTTP response builder helpers"
```

---

### Task 6: Test Fixtures

**Files:**
- Create: `tests/conftest.py`

Handlers import db and cache as modules (`from src import db, cache`), so patching `src.db.get_connection` and `src.cache.cache_get` intercepts all handler calls.

- [ ] **Step 1: Create `tests/conftest.py`**

```python
# tests/conftest.py
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_db(mocker):
    """Patches src.db.get_connection. Returns the mock cursor."""
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("src.db.get_connection", return_value=mock_conn)
    return mock_cursor


@pytest.fixture
def mock_cache(mocker):
    """Patches src.cache.cache_get (returns None by default) and src.cache.cache_set."""
    mock_get = mocker.patch("src.cache.cache_get", return_value=None)
    mock_set = mocker.patch("src.cache.cache_set")
    return mock_get, mock_set


@pytest.fixture
def api_event():
    """Base API Gateway proxy event with Cognito authorizer claims."""
    return {
        "httpMethod": "GET",
        "path": "/newsletters",
        "resource": "/newsletters",
        "pathParameters": None,
        "queryStringParameters": None,
        "headers": {"Authorization": "Bearer test-token"},
        "requestContext": {"authorizer": {"claims": {"sub": "user-test-123"}}},
        "body": None,
    }
```

- [ ] **Step 2: Verify fixtures load without errors**

```bash
pytest tests/ --collect-only -q
```

Expected: collection succeeds with no import errors.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: shared pytest fixtures for Lambda handler tests"
```

---

### Task 7: Newsletters Handler

**Files:**
- Create: `src/handlers/newsletters.py`
- Create: `tests/test_newsletters.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_newsletters.py
import json
import pytest


@pytest.fixture
def list_event(api_event):
    return {**api_event, "resource": "/newsletters", "path": "/newsletters"}


@pytest.fixture
def get_event(api_event):
    return {
        **api_event,
        "resource": "/newsletters/{newsletter_id}",
        "path": "/newsletters/nl-uuid-001",
        "pathParameters": {"newsletter_id": "nl-uuid-001"},
    }


def test_list_returns_cached_data(mock_cache, list_event):
    mock_get, _ = mock_cache
    mock_get.return_value = [{"newsletter_id": "nl-1", "title": "Tech Daily"}]

    from src.handlers.newsletters import handler
    resp = handler(list_event, {})

    assert resp["statusCode"] == 200
    assert json.loads(resp["body"]) == [{"newsletter_id": "nl-1", "title": "Tech Daily"}]


def test_list_queries_db_on_cache_miss(mock_db, mock_cache, list_event):
    mock_get, mock_set = mock_cache
    mock_get.return_value = None
    mock_db.fetchall.return_value = [
        {"newsletter_id": "nl-1", "topic_id": "t-1", "date": "2026-04-24", "title": "Tech Daily"}
    ]

    from src.handlers.newsletters import handler
    resp = handler(list_event, {})

    assert resp["statusCode"] == 200
    mock_db.execute.assert_called_once()
    mock_set.assert_called_once()


def test_get_by_id_returns_cached(mock_cache, get_event):
    mock_get, _ = mock_cache
    mock_get.return_value = {"newsletter_id": "nl-uuid-001", "title": "Tech", "events": []}

    from src.handlers.newsletters import handler
    resp = handler(get_event, {})

    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["newsletter_id"] == "nl-uuid-001"


def test_get_by_id_returns_404_when_not_found(mock_db, mock_cache, get_event):
    mock_cache[0].return_value = None
    mock_db.fetchall.return_value = []

    from src.handlers.newsletters import handler
    resp = handler(get_event, {})

    assert resp["statusCode"] == 404


def test_get_by_id_assembles_response_from_rows(mock_db, mock_cache, get_event):
    mock_cache[0].return_value = None
    mock_db.fetchall.side_effect = [
        [
            {
                "newsletter_id": "nl-uuid-001", "date": "2026-04-24",
                "title": "Tech Daily", "narrative": "Today in tech...",
                "position": 1, "event_id": "ev-001",
                "headline": "GPT-5.8 Released", "summary": "OpenAI released...",
                "event_date": "2026-04-24", "thread_id": "th-001",
                "thread_name": "GPT releases", "previous_event_id": None,
            }
        ],
        [
            {"reason": "Background on OpenAI", "position": 1,
             "newsletter_id": "nl-old", "date": "2026-04-02", "title": "Tech Apr 2"},
        ],
    ]

    from src.handlers.newsletters import handler
    resp = handler(get_event, {})

    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["title"] == "Tech Daily"
    assert len(body["events"]) == 1
    assert body["events"][0]["headline"] == "GPT-5.8 Released"
    assert len(body["context_links"]) == 1
    mock_cache[1].assert_called_once()
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_newsletters.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.handlers.newsletters'`

- [ ] **Step 3: Implement `src/handlers/newsletters.py`**

```python
# src/handlers/newsletters.py
import json
from src import db, cache
from src.response import ok, not_found

_TTL = 3600

_LIST_SQL = """
    SELECT DISTINCT ON (n.topic_id)
        n.newsletter_id, n.topic_id, n.date, n.title
    FROM newsletters n
    JOIN subscriptions s ON s.topic_id = n.topic_id
    WHERE s.user_id = %s
    ORDER BY n.topic_id, n.date DESC
"""

_GET_SQL = """
    SELECT
        n.newsletter_id, n.date, n.title, n.narrative,
        ne.position,
        e.event_id, e.headline, e.summary, e.date AS event_date,
        ne.thread_id, t.name AS thread_name,
        etm.previous_event_id
    FROM newsletters n
    JOIN newsletter_events ne  ON ne.newsletter_id = n.newsletter_id
    JOIN news_events e          ON e.event_id = ne.event_id
    JOIN event_thread_memberships etm
        ON etm.event_id = e.event_id AND etm.thread_id = ne.thread_id
    JOIN threads t              ON t.thread_id = ne.thread_id
    WHERE n.newsletter_id = %s
    ORDER BY ne.position
"""

_LINKS_SQL = """
    SELECT ncl.reason, ncl.position, n2.newsletter_id, n2.date, n2.title
    FROM newsletter_context_links ncl
    JOIN newsletters n2 ON n2.newsletter_id = ncl.linked_newsletter_id
    WHERE ncl.newsletter_id = %s
    ORDER BY ncl.position
"""


def handler(event, context):
    if "{newsletter_id}" in event.get("resource", "") and event["httpMethod"] == "GET":
        return _get_by_id(event)
    if event["httpMethod"] == "GET":
        return _list(event)
    return {"statusCode": 405, "body": json.dumps({"error": "Method not allowed"})}


def _user_id(event):
    return event["requestContext"]["authorizer"]["claims"]["sub"]


def _list(event):
    user_id = _user_id(event)
    key = f"newsletters:user:{user_id}:latest"
    hit = cache.cache_get(key)
    if hit is not None:
        return ok(hit)

    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(_LIST_SQL, (user_id,))
        rows = [dict(r) for r in cur.fetchall()]

    cache.cache_set(key, rows, ttl=_TTL)
    return ok(rows)


def _get_by_id(event):
    newsletter_id = event["pathParameters"]["newsletter_id"]
    key = f"newsletter:{newsletter_id}"
    hit = cache.cache_get(key)
    if hit is not None:
        return ok(hit)

    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(_GET_SQL, (newsletter_id,))
        rows = cur.fetchall()
        if not rows:
            return not_found("Newsletter not found")
        cur.execute(_LINKS_SQL, (newsletter_id,))
        links = [dict(r) for r in cur.fetchall()]

    first = dict(rows[0])
    result = {
        "newsletter_id": str(first["newsletter_id"]),
        "date": str(first["date"]),
        "title": first["title"],
        "narrative": first["narrative"],
        "context_links": [
            {**dict(r), "newsletter_id": str(dict(r)["newsletter_id"]), "date": str(dict(r)["date"])}
            for r in links
        ],
        "events": [
            {
                "position": dict(r)["position"],
                "event_id": str(dict(r)["event_id"]),
                "headline": dict(r)["headline"],
                "summary": dict(r)["summary"],
                "event_date": str(dict(r)["event_date"]),
                "thread_id": str(dict(r)["thread_id"]),
                "thread_name": dict(r)["thread_name"],
                "previous_event_id": str(dict(r)["previous_event_id"]) if dict(r)["previous_event_id"] else None,
            }
            for r in rows
        ],
    }
    cache.cache_set(key, result, ttl=_TTL)
    return ok(result)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_newsletters.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/handlers/newsletters.py tests/test_newsletters.py
git commit -m "feat: newsletters Lambda handler with Redis cache"
```

---

### Task 8: Subscriptions Handler

**Files:**
- Create: `src/handlers/subscriptions.py`
- Create: `tests/test_subscriptions.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_subscriptions.py
import json
import pytest


@pytest.fixture
def get_event(api_event):
    return {**api_event, "httpMethod": "GET", "resource": "/subscriptions"}


@pytest.fixture
def post_event(api_event):
    return {
        **api_event, "httpMethod": "POST", "resource": "/subscriptions",
        "body": json.dumps({"topic_id": "topic-uuid-001"}),
    }


@pytest.fixture
def delete_event(api_event):
    return {
        **api_event, "httpMethod": "DELETE",
        "resource": "/subscriptions/{topic_id}",
        "pathParameters": {"topic_id": "topic-uuid-001"},
    }


def test_list_returns_user_topics(mock_db, get_event):
    mock_db.fetchall.return_value = [
        {"topic_id": "t-1", "name": "technology", "subscribed_at": "2026-01-01T00:00:00+00:00"}
    ]
    from src.handlers.subscriptions import handler
    resp = handler(get_event, {})
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])[0]["name"] == "technology"


def test_post_returns_201(mock_db, post_event):
    mock_db.fetchone.return_value = {
        "topic_id": "topic-uuid-001", "name": "technology",
        "subscribed_at": "2026-04-24T00:00:00+00:00",
    }
    from src.handlers.subscriptions import handler
    resp = handler(post_event, {})
    assert resp["statusCode"] == 201
    mock_db.execute.assert_called_once()


def test_post_returns_400_when_topic_id_missing(api_event):
    event = {**api_event, "httpMethod": "POST", "resource": "/subscriptions", "body": "{}"}
    from src.handlers.subscriptions import handler
    assert handler(event, {})["statusCode"] == 400


def test_delete_returns_204(mock_db, delete_event):
    from src.handlers.subscriptions import handler
    resp = handler(delete_event, {})
    assert resp["statusCode"] == 204
    mock_db.execute.assert_called_once()
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_subscriptions.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.handlers.subscriptions'`

- [ ] **Step 3: Implement `src/handlers/subscriptions.py`**

```python
# src/handlers/subscriptions.py
import json
from src import db
from src.response import ok, created, no_content, bad_request

_LIST_SQL = """
    SELECT s.topic_id, t.name, s.subscribed_at
    FROM subscriptions s JOIN topics t ON t.topic_id = s.topic_id
    WHERE s.user_id = %s ORDER BY s.subscribed_at DESC
"""
_INSERT_SQL = """
    INSERT INTO subscriptions (user_id, topic_id) VALUES (%s, %s)
    ON CONFLICT (user_id, topic_id) DO NOTHING
    RETURNING topic_id,
        (SELECT name FROM topics WHERE topic_id = %s) AS name,
        subscribed_at
"""
_DELETE_SQL = "DELETE FROM subscriptions WHERE user_id = %s AND topic_id = %s"


def handler(event, context):
    method, resource = event["httpMethod"], event.get("resource", "")
    if method == "GET":
        return _list(event)
    if method == "POST":
        return _subscribe(event)
    if method == "DELETE" and "{topic_id}" in resource:
        return _unsubscribe(event)
    return {"statusCode": 405, "body": json.dumps({"error": "Method not allowed"})}


def _uid(event):
    return event["requestContext"]["authorizer"]["claims"]["sub"]


def _list(event):
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(_LIST_SQL, (_uid(event),))
        rows = cur.fetchall()
    return ok([{**dict(r), "topic_id": str(dict(r)["topic_id"]),
                "subscribed_at": str(dict(r)["subscribed_at"])} for r in rows])


def _subscribe(event):
    body = json.loads(event.get("body") or "{}")
    topic_id = body.get("topic_id")
    if not topic_id:
        return bad_request("topic_id is required")
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(_INSERT_SQL, (_uid(event), topic_id, topic_id))
        row = dict(cur.fetchone() or {"topic_id": topic_id, "name": None, "subscribed_at": None})
        conn.commit()
    return created({**row, "topic_id": str(row["topic_id"]), "subscribed_at": str(row.get("subscribed_at", ""))})


def _unsubscribe(event):
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(_DELETE_SQL, (_uid(event), event["pathParameters"]["topic_id"]))
        conn.commit()
    return no_content()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_subscriptions.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/handlers/subscriptions.py tests/test_subscriptions.py
git commit -m "feat: subscriptions Lambda handler (GET/POST/DELETE)"
```

---

### Task 9: Interactions Handler

**Files:**
- Create: `src/handlers/interactions.py`
- Create: `tests/test_interactions.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_interactions.py
import json
import pytest


@pytest.fixture
def post_event(api_event):
    return {
        **api_event, "httpMethod": "POST", "resource": "/interactions",
        "body": json.dumps({"event_id": "ev-uuid-001", "type": "click"}),
    }


def test_post_records_interaction_and_returns_201(mock_db, post_event):
    mock_db.fetchone.return_value = {"interaction_id": "ix-1", "created_at": "2026-04-24T00:00:00+00:00"}
    from src.handlers.interactions import handler
    resp = handler(post_event, {})
    assert resp["statusCode"] == 201
    mock_db.execute.assert_called_once()


def test_post_returns_400_when_event_id_missing(api_event):
    event = {**api_event, "httpMethod": "POST", "resource": "/interactions",
             "body": json.dumps({"type": "click"})}
    from src.handlers.interactions import handler
    assert handler(event, {})["statusCode"] == 400


def test_post_returns_400_when_type_invalid(api_event):
    event = {**api_event, "httpMethod": "POST", "resource": "/interactions",
             "body": json.dumps({"event_id": "ev-001", "type": "unknown"})}
    from src.handlers.interactions import handler
    assert handler(event, {})["statusCode"] == 400


def test_post_accepts_all_valid_types(mock_db, api_event):
    mock_db.fetchone.return_value = {"interaction_id": "ix-1", "created_at": "2026-04-24T00:00:00+00:00"}
    from src.handlers.interactions import handler
    for t in ("view", "click", "deep_dive"):
        event = {**api_event, "httpMethod": "POST", "resource": "/interactions",
                 "body": json.dumps({"event_id": "ev-001", "type": t})}
        assert handler(event, {})["statusCode"] == 201, f"Expected 201 for type={t}"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_interactions.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.handlers.interactions'`

- [ ] **Step 3: Implement `src/handlers/interactions.py`**

```python
# src/handlers/interactions.py
import json
from src import db
from src.response import created, bad_request

_VALID_TYPES = {"view", "click", "deep_dive"}
_INSERT_SQL = """
    INSERT INTO interactions (user_id, event_id, type) VALUES (%s, %s, %s)
    RETURNING interaction_id, created_at
"""


def handler(event, context):
    if event["httpMethod"] != "POST":
        return {"statusCode": 405, "body": json.dumps({"error": "Method not allowed"})}

    body = json.loads(event.get("body") or "{}")
    event_id = body.get("event_id")
    interaction_type = body.get("type")

    if not event_id:
        return bad_request("event_id is required")
    if interaction_type not in _VALID_TYPES:
        return bad_request(f"type must be one of: {', '.join(sorted(_VALID_TYPES))}")

    user_id = event["requestContext"]["authorizer"]["claims"]["sub"]
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(_INSERT_SQL, (user_id, event_id, interaction_type))
        row = dict(cur.fetchone())
        conn.commit()

    return created({"interaction_id": str(row["interaction_id"]), "created_at": str(row["created_at"])})
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_interactions.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/handlers/interactions.py tests/test_interactions.py
git commit -m "feat: interactions Lambda handler with type validation"
```

---

### Task 10: Deep-dive SSE Handler

**Files:**
- Create: `src/handlers/deep_dive.py`
- Create: `tests/test_deep_dive.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_deep_dive.py
import json
import pytest


@pytest.fixture
def deep_dive_event(api_event):
    return {
        **api_event, "httpMethod": "POST",
        "resource": "/deep-dive/{event_id}",
        "path": "/deep-dive/ev-uuid-001",
        "pathParameters": {"event_id": "ev-uuid-001"},
    }


def test_returns_200_with_sse_content_type(deep_dive_event):
    from src.handlers.deep_dive import handler
    resp = handler(deep_dive_event, {})
    assert resp["statusCode"] == 200
    assert resp["headers"]["Content-Type"] == "text/event-stream"


def test_body_contains_sse_data_lines(deep_dive_event):
    from src.handlers.deep_dive import handler
    lines = [l for l in handler(deep_dive_event, {})["body"].split("\n") if l.startswith("data:")]
    assert len(lines) >= 2  # at least one content chunk + terminal done chunk


def test_last_chunk_has_done_true(deep_dive_event):
    from src.handlers.deep_dive import handler
    data_lines = [l[6:] for l in handler(deep_dive_event, {})["body"].split("\n") if l.startswith("data:")]
    assert json.loads(data_lines[-1])["done"] is True


def test_non_last_chunks_have_done_false_and_content(deep_dive_event):
    from src.handlers.deep_dive import handler
    data_lines = [l[6:] for l in handler(deep_dive_event, {})["body"].split("\n") if l.startswith("data:")]
    for line in data_lines[:-1]:
        chunk = json.loads(line)
        assert chunk["done"] is False
        assert len(chunk["chunk"]) > 0


def test_returns_405_for_get(api_event):
    event = {**api_event, "httpMethod": "GET", "resource": "/deep-dive/{event_id}",
             "pathParameters": {"event_id": "ev-001"}}
    from src.handlers.deep_dive import handler
    assert handler(event, {})["statusCode"] == 405
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_deep_dive.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.handlers.deep_dive'`

- [ ] **Step 3: Implement `src/handlers/deep_dive.py`**

```python
# src/handlers/deep_dive.py
import json

_MOCK_CHUNKS = [
    "This event marks a significant development in the ongoing story.",
    " Historical context: previous events in this thread laid the groundwork.",
    " Industry analysts expect broad adoption within the next quarter.",
    " Related threads suggest this will accelerate parallel developments.",
]


def handler(event, context):
    if event["httpMethod"] != "POST":
        return {"statusCode": 405, "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Method not allowed"})}

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/event-stream", "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no"},
        "body": _build_sse(_MOCK_CHUNKS),
    }


def _build_sse(chunks: list[str]) -> str:
    lines = []
    for text in chunks:
        lines.append(f"data: {json.dumps({'chunk': text, 'done': False})}")
        lines.append("")
    lines.append(f"data: {json.dumps({'chunk': '', 'done': True})}")
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass (22 total across all test files).

- [ ] **Step 5: Commit**

```bash
git add src/handlers/deep_dive.py tests/test_deep_dive.py
git commit -m "feat: deep-dive SSE Lambda handler with mock chunks"
```

---

### Task 11: SAM Infrastructure Template

**Files:**
- Create: `infra/template.yaml`
- Create: `samconfig.toml`

- [ ] **Step 1: Create `infra/template.yaml`**

```yaml
# infra/template.yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Newsletter API Serving Layer

Parameters:
  Environment:
    Type: String
    Default: dev
    AllowedValues: [dev, prod]
  VpcId:
    Type: AWS::EC2::VPC::Id
  SubnetIds:
    Type: List<AWS::EC2::Subnet::Id>
  DbHost:
    Type: String
    Description: RDS Proxy endpoint
  DbName:
    Type: String
    Default: newsletter
  DbUser:
    Type: String
    Default: newsletter
  DbPassword:
    Type: String
    NoEcho: true
  RedisHost:
    Type: String
    Description: ElastiCache Serverless endpoint

Globals:
  Function:
    Runtime: python3.12
    Timeout: 29
    MemorySize: 256
    Environment:
      Variables:
        DB_HOST: !Ref DbHost
        DB_NAME: !Ref DbName
        DB_USER: !Ref DbUser
        DB_PASSWORD: !Ref DbPassword
        REDIS_HOST: !Ref RedisHost
        REDIS_SSL: "true"
    VpcConfig:
      SecurityGroupIds: [!Ref LambdaSG]
      SubnetIds: !Ref SubnetIds

Resources:
  LambdaSG:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Lambda outbound to Aurora and Redis
      VpcId: !Ref VpcId

  UserPool:
    Type: AWS::Cognito::UserPool
    Properties:
      UserPoolName: !Sub newsletter-${Environment}
      AutoVerifiedAttributes: [email]
      Policies:
        PasswordPolicy:
          MinimumLength: 8
          RequireUppercase: false
          RequireLowercase: false
          RequireNumbers: false
          RequireSymbols: false

  UserPoolClient:
    Type: AWS::Cognito::UserPoolClient
    Properties:
      UserPoolId: !Ref UserPool
      ExplicitAuthFlows: [ALLOW_USER_PASSWORD_AUTH, ALLOW_REFRESH_TOKEN_AUTH]
      GenerateSecret: false

  Api:
    Type: AWS::Serverless::Api
    Properties:
      StageName: !Ref Environment
      Auth:
        DefaultAuthorizer: CognitoAuth
        Authorizers:
          CognitoAuth:
            UserPoolArn: !GetAtt UserPool.Arn
      ThrottlingBurstLimit: 1000
      ThrottlingRateLimit: 1000

  NewslettersFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: ../
      Handler: src/handlers/newsletters.handler
      Events:
        List:
          Type: Api
          Properties:
            RestApiId: !Ref Api
            Path: /newsletters
            Method: GET
        Get:
          Type: Api
          Properties:
            RestApiId: !Ref Api
            Path: /newsletters/{newsletter_id}
            Method: GET

  SubscriptionsFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: ../
      Handler: src/handlers/subscriptions.handler
      Events:
        List:
          Type: Api
          Properties:
            RestApiId: !Ref Api
            Path: /subscriptions
            Method: GET
        Subscribe:
          Type: Api
          Properties:
            RestApiId: !Ref Api
            Path: /subscriptions
            Method: POST
        Unsubscribe:
          Type: Api
          Properties:
            RestApiId: !Ref Api
            Path: /subscriptions/{topic_id}
            Method: DELETE

  InteractionsFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: ../
      Handler: src/handlers/interactions.handler
      Events:
        Post:
          Type: Api
          Properties:
            RestApiId: !Ref Api
            Path: /interactions
            Method: POST

  DeepDiveFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: ../
      Handler: src/handlers/deep_dive.handler
      Timeout: 60
      FunctionResponseTypes: [StreamAndBuffer]
      Events:
        Post:
          Type: Api
          Properties:
            RestApiId: !Ref Api
            Path: /deep-dive/{event_id}
            Method: POST

Outputs:
  ApiUrl:
    Value: !Sub https://${Api}.execute-api.${AWS::Region}.amazonaws.com/${Environment}
  UserPoolId:
    Value: !Ref UserPool
  UserPoolClientId:
    Value: !Ref UserPoolClient
```

- [ ] **Step 2: Create `samconfig.toml`**

```toml
version = 0.1

[dev.deploy.parameters]
stack_name = "newsletter-api-dev"
region = "eu-west-1"
confirm_changeset = true
capabilities = "CAPABILITY_IAM"
parameter_overrides = "Environment=dev"
```

- [ ] **Step 3: Validate template**

```bash
sam validate --template infra/template.yaml --lint
```

Expected: `infra/template.yaml is a valid SAM Template`

- [ ] **Step 4: Commit**

```bash
git add infra/template.yaml samconfig.toml
git commit -m "feat: SAM template — Lambda, API Gateway, Cognito"
```

---

### Task 12: Mock Data Seed Script

**Files:**
- Create: `scripts/seed.py`

- [ ] **Step 1: Write `scripts/seed.py`**

```python
#!/usr/bin/env python3
# scripts/seed.py
"""
Truncates all tables, inserts mock data, and pre-warms Redis.
Usage: python scripts/seed.py
Env vars (all optional, default to local Docker values):
  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
  REDIS_HOST, REDIS_PORT, REDIS_SSL
"""
import os, sys, json, uuid
from datetime import date, timedelta
import psycopg2, psycopg2.extras, redis

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


def db():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "newsletter"),
        user=os.environ.get("DB_USER", "newsletter"),
        password=os.environ.get("DB_PASSWORD", "newsletter"),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def redis_client():
    return redis.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        ssl=os.environ.get("REDIS_SSL", "false").lower() == "true",
        decode_responses=True,
    )


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


if __name__ == "__main__":
    conn = db()
    rc = redis_client()
    try:
        seed(conn, rc)
    except Exception as e:
        conn.rollback()
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()
```

- [ ] **Step 2: Run seed against local Docker**

```bash
python scripts/seed.py
```

Expected:
```
Truncating...
  topics: 3
  threads: 15
  news_events: 300
  newsletters: 90
  context_links: inserted
  subscriptions: 1000 users × 2 topics
  interactions: 10000
Pre-warming Redis...
Redis pre-warmed.
✓ Seed complete
```

- [ ] **Step 3: Verify row counts**

```bash
docker compose exec postgres psql -U newsletter -d newsletter -c \
  "SELECT (SELECT count(*) FROM topics) t, (SELECT count(*) FROM threads) th, \
          (SELECT count(*) FROM news_events) ev, (SELECT count(*) FROM newsletters) nl, \
          (SELECT count(*) FROM subscriptions) sub, (SELECT count(*) FROM interactions) ix;"
```

Expected: `3 | 15 | 300 | 90 | 2000 | 10000`

- [ ] **Step 4: Commit**

```bash
git add scripts/seed.py
git commit -m "feat: mock data seed script with Redis pre-warm"
```

---

### Task 13: k6 Load Test Scripts

**Files:**
- Create: `load_tests/config.js`
- Create: `load_tests/newsletter_cached.js`
- Create: `load_tests/newsletter_cold.js`
- Create: `load_tests/mixed_realistic.js`
- Create: `load_tests/deep_dive_sse.js`
- Create: `load_tests/cold_start_stress.js`

- [ ] **Step 1: Create `load_tests/config.js`**

```javascript
// load_tests/config.js
export const BASE_URL = __ENV.API_URL || "";
export const headers = {
  Authorization: `Bearer ${__ENV.COGNITO_TOKEN || ""}`,
  "Content-Type": "application/json",
};
export const NEWSLETTER_IDS = (__ENV.NEWSLETTER_IDS || "").split(",").filter(Boolean);
export const EVENT_IDS      = (__ENV.EVENT_IDS      || "").split(",").filter(Boolean);
```

- [ ] **Step 2: Create `load_tests/newsletter_cached.js`**

```javascript
// load_tests/newsletter_cached.js
import http from "k6/http";
import { check, sleep } from "k6";
import { BASE_URL, headers, NEWSLETTER_IDS } from "./config.js";

export const options = {
  vus: 500, duration: "60s",
  thresholds: { http_req_duration: ["p(99)<50"], http_req_failed: ["rate<0.001"] },
};

export default function () {
  const id = NEWSLETTER_IDS[Math.floor(Math.random() * NEWSLETTER_IDS.length)];
  const res = http.get(`${BASE_URL}/newsletters/${id}`, { headers });
  check(res, { "200": (r) => r.status === 200, "has newsletter_id": (r) => !!JSON.parse(r.body).newsletter_id });
  sleep(0.1);
}
```

- [ ] **Step 3: Create `load_tests/newsletter_cold.js`**

```javascript
// load_tests/newsletter_cold.js
import http from "k6/http";
import { check } from "k6";
import { BASE_URL, headers, NEWSLETTER_IDS } from "./config.js";

export const options = {
  vus: 200, duration: "60s",
  thresholds: { http_req_duration: ["p(99)<300"], http_req_failed: ["rate<0.001"] },
};

export default function () {
  // Unique query param prevents CDN caching; Redis key ignores it so this hits Aurora
  const id = NEWSLETTER_IDS[Math.floor(Math.random() * NEWSLETTER_IDS.length)];
  check(http.get(`${BASE_URL}/newsletters/${id}?_cb=${Date.now()}`, { headers }),
        { "200": (r) => r.status === 200 });
}
```

- [ ] **Step 4: Create `load_tests/mixed_realistic.js`**

```javascript
// load_tests/mixed_realistic.js
import http from "k6/http";
import { check, sleep } from "k6";
import { BASE_URL, headers, NEWSLETTER_IDS, EVENT_IDS } from "./config.js";

export const options = {
  vus: 1000, duration: "120s",
  thresholds: { http_req_duration: ["p(95)<200"], http_req_failed: ["rate<0.01"] },
};

const TYPES = ["view", "click", "deep_dive"];

export default function () {
  const roll = Math.random();
  if (roll < 0.6) {
    const id = NEWSLETTER_IDS[Math.floor(Math.random() * NEWSLETTER_IDS.length)];
    check(http.get(`${BASE_URL}/newsletters/${id}`, { headers }), { "nl 200": (r) => r.status === 200 });
  } else if (roll < 0.9) {
    const event_id = EVENT_IDS[Math.floor(Math.random() * EVENT_IDS.length)];
    check(http.post(`${BASE_URL}/interactions`,
          JSON.stringify({ event_id, type: TYPES[Math.floor(Math.random() * TYPES.length)] }), { headers }),
          { "ix 201": (r) => r.status === 201 });
  } else {
    check(http.get(`${BASE_URL}/subscriptions`, { headers }), { "sub 200": (r) => r.status === 200 });
  }
  sleep(0.05);
}
```

- [ ] **Step 5: Create `load_tests/deep_dive_sse.js`**

```javascript
// load_tests/deep_dive_sse.js
import http from "k6/http";
import { check } from "k6";
import { BASE_URL, headers, EVENT_IDS } from "./config.js";

export const options = {
  vus: 50, duration: "60s",
  thresholds: { http_req_duration: ["p(95)<5000"], http_req_failed: ["rate<0.01"] },
};

export default function () {
  const id = EVENT_IDS[Math.floor(Math.random() * EVENT_IDS.length)];
  const res = http.post(`${BASE_URL}/deep-dive/${id}`, null, { headers });
  check(res, {
    "200": (r) => r.status === 200,
    "SSE content-type": (r) => (r.headers["Content-Type"] || "").includes("text/event-stream"),
    "done:true present": (r) => r.body.includes('"done":true') || r.body.includes('"done": true'),
  });
}
```

- [ ] **Step 6: Create `load_tests/cold_start_stress.js`**

```javascript
// load_tests/cold_start_stress.js
import http from "k6/http";
import { check } from "k6";
import { BASE_URL, headers, NEWSLETTER_IDS } from "./config.js";

export const options = {
  stages: [
    { duration: "10s", target: 1000 },
    { duration: "30s", target: 1000 },
    { duration: "10s", target: 0 },
  ],
  thresholds: { http_req_failed: ["rate<0.01"] },
};

export default function () {
  const id = NEWSLETTER_IDS[Math.floor(Math.random() * NEWSLETTER_IDS.length)];
  check(http.get(`${BASE_URL}/newsletters/${id}`, { headers }), { "not 5xx": (r) => r.status < 500 });
}
```

- [ ] **Step 7: Commit**

```bash
git add load_tests/
git commit -m "feat: k6 load test scenarios (cached, cold, mixed, SSE, cold-start)"
```

---

### Task 14: Cognito Test Token Script

**Files:**
- Create: `scripts/create_test_tokens.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
# scripts/create_test_tokens.py
"""
Creates 100 Cognito test users and prints Bearer tokens to stdout.
Run once after SAM deploy.
Usage: python scripts/create_test_tokens.py
Env vars: AWS_REGION, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID
"""
import os, sys, boto3
from botocore.exceptions import ClientError

REGION    = os.environ.get("AWS_REGION", "eu-west-1")
POOL_ID   = os.environ["COGNITO_USER_POOL_ID"]
CLIENT_ID = os.environ["COGNITO_CLIENT_ID"]
PASSWORD  = "TestPass123!"
N_USERS   = 100

idp = boto3.client("cognito-idp", region_name=REGION)


def token_for(n: int) -> str:
    username = f"loadtest{n:03d}@example.com"
    try:
        idp.admin_create_user(UserPoolId=POOL_ID, Username=username,
                              TemporaryPassword=PASSWORD, MessageAction="SUPPRESS")
    except ClientError as e:
        if e.response["Error"]["Code"] != "UsernameExistsException":
            raise
    idp.admin_set_user_password(UserPoolId=POOL_ID, Username=username,
                                Password=PASSWORD, Permanent=True)
    resp = idp.initiate_auth(AuthFlow="USER_PASSWORD_AUTH",
                             AuthParameters={"USERNAME": username, "PASSWORD": PASSWORD},
                             ClientId=CLIENT_ID)
    return resp["AuthenticationResult"]["IdToken"]


if __name__ == "__main__":
    tokens = []
    for i in range(N_USERS):
        try:
            tokens.append(token_for(i))
            if i % 10 == 0:
                print(f"  {i}/{N_USERS}", file=sys.stderr)
        except Exception as e:
            print(f"  user {i} failed: {e}", file=sys.stderr)

    print("\n".join(tokens))
    print(f"\n✓ {len(tokens)} tokens. Use first as COGNITO_TOKEN:", file=sys.stderr)
    print(f"  export COGNITO_TOKEN=$(python scripts/create_test_tokens.py | head -1)", file=sys.stderr)
```

- [ ] **Step 2: Commit**

```bash
git add scripts/create_test_tokens.py
git commit -m "feat: Cognito test user and token generation script"
```

---

## Running the Load Tests

After deploying via `sam deploy` and running `seed.py` against the live database:

```bash
# 1. Get a token
export COGNITO_TOKEN=$(python scripts/create_test_tokens.py | head -1)
export API_URL=https://<api-id>.execute-api.eu-west-1.amazonaws.com/dev

# 2. Get newsletter and event IDs from Aurora (or seed script output)
export NEWSLETTER_IDS=nl-id-1,nl-id-2,nl-id-3
export EVENT_IDS=ev-id-1,ev-id-2,ev-id-3

# 3. Run a scenario
k6 run -e API_URL=$API_URL -e COGNITO_TOKEN=$COGNITO_TOKEN \
       -e NEWSLETTER_IDS=$NEWSLETTER_IDS -e EVENT_IDS=$EVENT_IDS \
       load_tests/mixed_realistic.js
```
