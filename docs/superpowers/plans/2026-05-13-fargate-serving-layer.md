# Fargate Serving Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Lambda + API Gateway with async FastAPI on ECS Fargate, keeping all existing infrastructure (VPC, Aurora PostgreSQL, ElastiCache Redis, Cognito).

**Architecture:** FastAPI app with asyncpg + redis.asyncio runs in ECS Fargate tasks behind an ALB. Cognito JWT is verified in-process via python-jose + JWKS. All existing VPC SGs are extended (not replaced) by adding `aws_security_group_rule` resources in a new `terraform/modules/fargate/` module.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, asyncpg, redis.asyncio, python-jose[cryptography], Terraform ~>5.0, k6

---

## File Structure

### New files
| File | Responsibility |
|---|---|
| `src/main.py` | FastAPI app, lifespan (pool+redis init), router registration, `/health` |
| `src/auth.py` | JWKS fetch (lru_cache), RS256 verify → `sub` claim |
| `src/db_async.py` | `create_pool()` — asyncpg pool factory |
| `src/cache_async.py` | `create_redis()` — redis.asyncio client factory |
| `src/dependencies.py` | `get_pool`, `get_redis`, `get_user_id` Depends providers |
| `requirements-fargate.txt` | Runtime deps for Fargate image |
| `Dockerfile` | python:3.12-slim, uvicorn entrypoint |
| `tests/test_auth.py` | Unit tests for auth.verify |
| `tests/test_main.py` | Health endpoint + router smoke tests |
| `terraform/modules/fargate/main.tf` | All Fargate AWS resources |
| `terraform/modules/fargate/variables.tf` | Module inputs |
| `terraform/modules/fargate/outputs.tf` | alb_dns, ecr_repo_url, cluster_name, service_name |
| `load_tests/capacity_benchmark.js` | Stepped VU ramp, no thresholds — calibration only |
| `scripts/scale_up.py` | AWS CLI: set desired_count=2, poll until RUNNING |
| `scripts/scale_down.py` | AWS CLI: set desired_count=0 |
| `scripts/deploy_fargate.sh` | docker build + ECR push + ecs force-new-deployment |

### Modified files
| File | Change |
|---|---|
| `src/fields.py` | Add `EnvVar.DEEP_DIVE_INTERVAL`, `EnvVar.COGNITO_USER_POOL_ID`, `EnvVar.AWS_REGION` |
| `src/handlers/newsletters.py` | Rewrite as async FastAPI router (asyncpg, redis.asyncio) |
| `src/handlers/subscriptions.py` | Rewrite as async FastAPI router |
| `src/handlers/interactions.py` | Rewrite as async FastAPI router + Pydantic body |
| `src/handlers/deep_dive.py` | Rewrite as StreamingResponse + parametric SSE generator |
| `tests/conftest.py` | Add `mock_pool`, `mock_redis` fixtures (keep old Lambda fixtures) |
| `tests/test_newsletters.py` | Full rewrite for FastAPI TestClient |
| `tests/test_subscriptions.py` | Full rewrite for FastAPI TestClient |
| `tests/test_interactions.py` | Full rewrite for FastAPI TestClient |
| `tests/test_deep_dive.py` | Full rewrite for FastAPI TestClient |
| `terraform/envs/dev/main.tf` | Add `module "fargate"` block |
| `terraform/envs/dev/variables.tf` | Add `cognito_user_pool_id`, `fargate_uvicorn_workers` |
| `terraform/envs/dev/outputs.tf` | Add `alb_dns`, `ecr_repo_url`, `ecs_cluster`, `ecs_service` |
| `load_tests/newsletter_uncached.js` | Threshold p99 300ms → 100ms |
| `load_tests/mixed_realistic.js` | Threshold p95 200ms → 150ms |
| `load_tests/deep_dive_sse.js` | Threshold p95 5000ms → 500ms |
| `scripts/steps.py` | Add DEPLOY/SCALE_UP/BENCHMARK/SCALE_DOWN + FARGATE_STEP_ORDER |
| `scripts/pipeline.py` | Add `--runtime fargate|lambda`, Fargate pipeline with scale_down finally |
| `scripts/paths.py` | Add DEPLOY_FARGATE_SCRIPT, SCALE_UP_SCRIPT, SCALE_DOWN_SCRIPT |
| `config/dev.yaml` | Add `fargate.alb_url` key (filled after terraform apply) |

---

## Task 1: Add env vars to src/fields.py

**Files:**
- Modify: `src/fields.py`

- [ ] **Step 1: Add three constants to EnvVar**

In `src/fields.py`, add to the `EnvVar` class:

```python
class EnvVar(StrEnum):
    DB_HOST = "DB_HOST"
    DB_NAME = "DB_NAME"
    DB_USER = "DB_USER"
    DB_PASSWORD = "DB_PASSWORD"
    DB_PORT = "DB_PORT"
    REDIS_HOST = "REDIS_HOST"
    REDIS_PORT = "REDIS_PORT"
    REDIS_SSL = "REDIS_SSL"
    COGNITO_USER_POOL_ID = "COGNITO_USER_POOL_ID"
    AWS_REGION = "AWS_REGION"
    DEEP_DIVE_INTERVAL = "DEEP_DIVE_INTERVAL"
```

- [ ] **Step 2: Run existing tests to confirm nothing broke**

```bash
pytest tests/ -v
```

Expected: all tests pass, no new failures.

- [ ] **Step 3: Commit**

```bash
git add src/fields.py
git commit -m "feat(fields): add COGNITO_USER_POOL_ID, AWS_REGION, DEEP_DIVE_INTERVAL env vars"
```

---

## Task 2: requirements-fargate.txt + Dockerfile

**Files:**
- Create: `requirements-fargate.txt`
- Create: `Dockerfile`

- [ ] **Step 1: Create requirements-fargate.txt at project root**

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
asyncpg>=0.29.0
redis[asyncio]>=5.0.0
python-jose[cryptography]>=3.3.0
pydantic>=2.0.0
httpx>=0.27.0
```

(`httpx` is required by FastAPI's `TestClient` starting with Starlette ≥ 0.21.)

- [ ] **Step 2: Create Dockerfile at project root**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements-fargate.txt .
RUN pip install --no-cache-dir -r requirements-fargate.txt
COPY src/ ./src/
WORKDIR /app/src
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1}"]
```

- [ ] **Step 3: Install deps locally for testing**

```bash
pip install -r requirements-fargate.txt
```

Expected: installs without conflict.

- [ ] **Step 4: Commit**

```bash
git add requirements-fargate.txt Dockerfile
git commit -m "chore: add requirements-fargate.txt and Dockerfile for Fargate image"
```

---

## Task 3: src/auth.py — JWT verification

**Files:**
- Create: `src/auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_auth.py`:

```python
import pytest
from unittest.mock import patch
from fastapi import HTTPException
from jose import JWTError


def test_verify_returns_sub_on_valid_token():
    import auth
    with patch("auth._fetch_jwks", return_value={"keys": [{"kid": "k1", "kty": "RSA"}]}):
        auth._jwks.cache_clear()
        with patch("auth.jwt.get_unverified_header", return_value={"kid": "k1"}):
            with patch("auth.jwt.decode", return_value={"sub": "user-123"}):
                assert auth.verify("valid.token.here") == "user-123"


def test_verify_raises_401_on_unknown_kid():
    import auth
    with patch("auth._fetch_jwks", return_value={"keys": [{"kid": "other-kid"}]}):
        auth._jwks.cache_clear()
        with patch("auth.jwt.get_unverified_header", return_value={"kid": "unknown"}):
            with pytest.raises(HTTPException) as exc:
                auth.verify("bad.token")
            assert exc.value.status_code == 401


def test_verify_raises_401_on_jwt_error():
    import auth
    with patch("auth._fetch_jwks", return_value={"keys": [{"kid": "k1"}]}):
        auth._jwks.cache_clear()
        with patch("auth.jwt.get_unverified_header", return_value={"kid": "k1"}):
            with patch("auth.jwt.decode", side_effect=JWTError("expired")):
                with pytest.raises(HTTPException) as exc:
                    auth.verify("expired.token")
                assert exc.value.status_code == 401


def test_verify_raises_401_on_missing_sub():
    import auth
    with patch("auth._fetch_jwks", return_value={"keys": [{"kid": "k1"}]}):
        auth._jwks.cache_clear()
        with patch("auth.jwt.get_unverified_header", return_value={"kid": "k1"}):
            with patch("auth.jwt.decode", return_value={}):
                with pytest.raises(HTTPException) as exc:
                    auth.verify("no-sub.token")
                assert exc.value.status_code == 401
```

- [ ] **Step 2: Run — confirm FAIL**

```bash
pytest tests/test_auth.py -v
```

Expected: `ModuleNotFoundError: No module named 'auth'`

- [ ] **Step 3: Create src/auth.py**

```python
import functools
import json
import os
import urllib.request

from fastapi import HTTPException
from jose import JWTError, jwt

from fields import EnvVar


def _fetch_jwks() -> dict:
    region = os.environ[EnvVar.AWS_REGION]
    pool_id = os.environ[EnvVar.COGNITO_USER_POOL_ID]
    url = f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json"
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


@functools.lru_cache(maxsize=1)
def _jwks() -> dict:
    return _fetch_jwks()


def verify(token: str) -> str:
    try:
        header = jwt.get_unverified_header(token)
        keys = {k["kid"]: k for k in _jwks()["keys"]}
        key = keys.get(header.get("kid"))
        if key is None:
            raise HTTPException(status_code=401, detail="Unknown signing key")
        payload = jwt.decode(token, key, algorithms=["RS256"])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Missing sub claim")
        return sub
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
```

- [ ] **Step 4: Run — confirm PASS**

```bash
pytest tests/test_auth.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/auth.py tests/test_auth.py
git commit -m "feat(auth): JWT RS256 verification via Cognito JWKS"
```

---

## Task 4: src/db_async.py + src/cache_async.py

**Files:**
- Create: `src/db_async.py`
- Create: `src/cache_async.py`

- [ ] **Step 1: Create src/db_async.py**

```python
import os

import asyncpg

from fields import EnvVar


async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        host=os.environ[EnvVar.DB_HOST],
        port=int(os.environ.get(EnvVar.DB_PORT, "5432")),
        database=os.environ[EnvVar.DB_NAME],
        user=os.environ[EnvVar.DB_USER],
        password=os.environ[EnvVar.DB_PASSWORD],
        min_size=5,
        max_size=20,
        command_timeout=5,
    )
```

- [ ] **Step 2: Create src/cache_async.py**

```python
import os

import redis.asyncio as aioredis

from fields import EnvVar


async def create_redis() -> aioredis.Redis:
    ssl = os.environ.get(EnvVar.REDIS_SSL, "false").lower() == "true"
    return aioredis.Redis(
        host=os.environ[EnvVar.REDIS_HOST],
        port=int(os.environ.get(EnvVar.REDIS_PORT, "6379")),
        decode_responses=True,
        ssl=ssl,
    )
```

- [ ] **Step 3: Run full suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/db_async.py src/cache_async.py
git commit -m "feat(db): asyncpg pool factory and redis.asyncio client factory"
```

---

## Task 5: src/dependencies.py

**Files:**
- Create: `src/dependencies.py`

- [ ] **Step 1: Create src/dependencies.py**

```python
import asyncpg
import redis.asyncio as aioredis
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

import auth

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


async def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


async def get_user_id(token: str = Depends(oauth2_scheme)) -> str:
    return auth.verify(token)
```

- [ ] **Step 2: Run full suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/dependencies.py
git commit -m "feat(dependencies): FastAPI Depends providers for pool, redis, user_id"
```

---

## Task 6: Update tests/conftest.py

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add mock_pool and mock_redis fixtures (keep all existing fixtures)**

Replace `tests/conftest.py` with:

```python
import pytest
from unittest.mock import MagicMock, AsyncMock
from fields import LambdaEvent, HttpHeader


# --- Lambda fixtures (used by test_db.py, test_cache.py, test_response.py) ---

@pytest.fixture
def mock_db(mocker):
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mocker.patch("db.get_connection", return_value=mock_conn)
    return mock_cursor


@pytest.fixture
def mock_cache(mocker):
    mock_get = mocker.patch("cache.cache_get", return_value=None)
    mock_set = mocker.patch("cache.cache_set")
    return mock_get, mock_set


@pytest.fixture
def api_event():
    return {
        LambdaEvent.HTTP_METHOD: "GET",
        LambdaEvent.PATH: "/newsletters",
        LambdaEvent.RESOURCE: "/newsletters",
        LambdaEvent.PATH_PARAMETERS: None,
        LambdaEvent.QUERY_STRING_PARAMETERS: None,
        LambdaEvent.HEADERS: {HttpHeader.AUTHORIZATION: "Bearer test-token"},
        LambdaEvent.REQUEST_CONTEXT: {
            LambdaEvent.AUTHORIZER: {
                LambdaEvent.CLAIMS: {
                    LambdaEvent.SUB: "user-test-123",
                }
            }
        },
        LambdaEvent.BODY: None,
    }


# --- FastAPI fixtures ---

@pytest.fixture
def mock_pool():
    return AsyncMock()


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get.return_value = None
    return redis
```

- [ ] **Step 2: Run full suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test(conftest): add mock_pool and mock_redis FastAPI fixtures"
```

---

## Task 7: Rewrite src/handlers/newsletters.py + tests

**Files:**
- Modify: `src/handlers/newsletters.py`
- Modify: `tests/test_newsletters.py`

Each test file creates its own mini FastAPI app with only the newsletter router. This isolates tests from `main.py`.

- [ ] **Step 1: Write failing tests**

Replace `tests/test_newsletters.py` entirely:

```python
import json
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fields import NewsletterField, EventField, ContextLinkField, HttpHeader, CacheStatus

_USER_ID = "test-user-sub"


def _make_client(pool: AsyncMock, redis: AsyncMock) -> TestClient:
    from handlers.newsletters import router
    from dependencies import get_pool, get_redis, get_user_id
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_user_id] = lambda: _USER_ID
    return TestClient(app)


# --- GET /newsletters ---

def test_list_returns_200_on_cache_hit():
    redis = AsyncMock()
    redis.get.return_value = json.dumps([{NewsletterField.ID: "nl-1", NewsletterField.TITLE: "Tech"}])
    pool = AsyncMock()
    resp = _make_client(pool, redis).get("/newsletters")
    assert resp.status_code == 200
    assert resp.json()[0][NewsletterField.ID] == "nl-1"
    assert resp.headers.get("x-lambda-cache") == CacheStatus.HIT


def test_list_does_not_query_pool_on_cache_hit():
    redis = AsyncMock()
    redis.get.return_value = json.dumps([])
    pool = AsyncMock()
    _make_client(pool, redis).get("/newsletters")
    pool.fetch.assert_not_called()


def test_list_queries_pool_on_cache_miss():
    redis = AsyncMock()
    redis.get.return_value = None
    pool = AsyncMock()
    pool.fetch.return_value = [
        {NewsletterField.ID: "nl-1", NewsletterField.TOPIC_ID: "t-1",
         NewsletterField.DATE: "2026-04-24", NewsletterField.TITLE: "Tech Daily"}
    ]
    resp = _make_client(pool, redis).get("/newsletters")
    assert resp.status_code == 200
    assert resp.headers.get("x-lambda-cache") == CacheStatus.MISS
    pool.fetch.assert_called_once()
    redis.set.assert_called_once()


def test_list_returns_401_without_auth():
    from handlers.newsletters import router
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app, raise_server_exceptions=False).get("/newsletters")
    assert resp.status_code == 401


# --- GET /newsletters/{newsletter_id} ---

def test_get_by_id_returns_cache_hit():
    redis = AsyncMock()
    redis.get.return_value = json.dumps({NewsletterField.ID: "nl-1", NewsletterField.TITLE: "Tech", NewsletterField.EVENTS: []})
    pool = AsyncMock()
    resp = _make_client(pool, redis).get("/newsletters/nl-1")
    assert resp.status_code == 200
    assert resp.json()[NewsletterField.ID] == "nl-1"
    assert resp.headers.get("x-lambda-cache") == CacheStatus.HIT
    pool.fetch.assert_not_called()


def test_get_by_id_returns_404_when_not_found():
    redis = AsyncMock()
    redis.get.return_value = None
    pool = AsyncMock()
    pool.fetch.return_value = []
    resp = _make_client(pool, redis).get("/newsletters/missing")
    assert resp.status_code == 404


def test_get_by_id_assembles_response_from_rows():
    redis = AsyncMock()
    redis.get.return_value = None
    pool = AsyncMock()
    pool.fetch.side_effect = [
        # _GET_SQL rows
        [{
            NewsletterField.ID: "nl-1", NewsletterField.DATE: "2026-04-24",
            NewsletterField.TITLE: "Tech Daily", NewsletterField.NARRATIVE: "Today...",
            EventField.POSITION: 1, EventField.ID: "ev-1",
            EventField.HEADLINE: "Headline", EventField.SUMMARY: "Summary",
            EventField.EVENT_DATE: "2026-04-24", EventField.THREAD_ID: "th-1",
            EventField.THREAD_NAME: "Thread A", EventField.PREVIOUS_EVENT_ID: None,
        }],
        # _LINKS_SQL rows
        [{
            ContextLinkField.REASON: "Background", ContextLinkField.POSITION: 1,
            ContextLinkField.NEWSLETTER_ID: "nl-old", ContextLinkField.DATE: "2026-04-01",
            ContextLinkField.TITLE: "Old Tech",
        }],
    ]
    resp = _make_client(pool, redis).get("/newsletters/nl-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body[NewsletterField.TITLE] == "Tech Daily"
    assert len(body[NewsletterField.EVENTS]) == 1
    assert body[NewsletterField.EVENTS][0][EventField.HEADLINE] == "Headline"
    assert len(body[NewsletterField.CONTEXT_LINKS]) == 1
    assert resp.headers.get("x-lambda-cache") == CacheStatus.MISS
    redis.set.assert_called_once()
```

- [ ] **Step 2: Run — confirm FAIL**

```bash
pytest tests/test_newsletters.py -v
```

Expected: `ImportError` or `AttributeError` — no `router` in old `handlers/newsletters.py`.

- [ ] **Step 3: Rewrite src/handlers/newsletters.py as FastAPI router**

```python
import json

import asyncpg
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from dependencies import get_pool, get_redis, get_user_id
from fields import (
    CachePrefix, CacheStatus, ContextLinkField,
    EventField, HttpHeader, NewsletterField,
)

router = APIRouter()

_TTL = 3600

_LIST_SQL = """
    SELECT DISTINCT ON (n.topic_id)
        n.newsletter_id, n.topic_id, n.date, n.title
    FROM newsletters n
    JOIN subscriptions s ON s.topic_id = n.topic_id
    WHERE s.user_id = $1
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
    WHERE n.newsletter_id = $1
    ORDER BY ne.position
"""

_LINKS_SQL = """
    SELECT ncl.reason, ncl.position, n2.newsletter_id, n2.date, n2.title
    FROM newsletter_context_links ncl
    JOIN newsletters n2 ON n2.newsletter_id = ncl.linked_newsletter_id
    WHERE ncl.newsletter_id = $1
    ORDER BY ncl.position
"""


@router.get("/newsletters")
async def list_newsletters(
    pool: asyncpg.Pool = Depends(get_pool),
    redis=Depends(get_redis),
    user_id: str = Depends(get_user_id),
):
    key = f"{CachePrefix.USER_LATEST}{user_id}:latest"
    hit = await redis.get(key)
    if hit:
        return JSONResponse(json.loads(hit), headers={HttpHeader.X_CACHE: CacheStatus.HIT})
    rows = await pool.fetch(_LIST_SQL, user_id)
    result = [dict(r) for r in rows]
    await redis.set(key, json.dumps(result, default=str), ex=_TTL)
    return JSONResponse(result, headers={HttpHeader.X_CACHE: CacheStatus.MISS})


@router.get("/newsletters/{newsletter_id}")
async def get_newsletter(
    newsletter_id: str,
    pool: asyncpg.Pool = Depends(get_pool),
    redis=Depends(get_redis),
    user_id: str = Depends(get_user_id),
):
    key = f"{CachePrefix.NEWSLETTER}{newsletter_id}"
    hit = await redis.get(key)
    if hit:
        return JSONResponse(json.loads(hit), headers={HttpHeader.X_CACHE: CacheStatus.HIT})

    rows = await pool.fetch(_GET_SQL, newsletter_id)
    if not rows:
        return JSONResponse({"error": "Newsletter not found"}, status_code=404)
    links = await pool.fetch(_LINKS_SQL, newsletter_id)

    first = dict(rows[0])
    result = {
        NewsletterField.ID: str(first[NewsletterField.ID]),
        NewsletterField.DATE: str(first[NewsletterField.DATE]),
        NewsletterField.TITLE: first[NewsletterField.TITLE],
        NewsletterField.NARRATIVE: first[NewsletterField.NARRATIVE],
        NewsletterField.CONTEXT_LINKS: [
            {
                **dict(r),
                ContextLinkField.NEWSLETTER_ID: str(dict(r)[ContextLinkField.NEWSLETTER_ID]),
                ContextLinkField.DATE: str(dict(r)[ContextLinkField.DATE]),
            }
            for r in links
        ],
        NewsletterField.EVENTS: [
            {
                EventField.POSITION: dict(r)[EventField.POSITION],
                EventField.ID: str(dict(r)[EventField.ID]),
                EventField.HEADLINE: dict(r)[EventField.HEADLINE],
                EventField.SUMMARY: dict(r)[EventField.SUMMARY],
                EventField.EVENT_DATE: str(dict(r)[EventField.EVENT_DATE]),
                EventField.THREAD_ID: str(dict(r)[EventField.THREAD_ID]),
                EventField.THREAD_NAME: dict(r)[EventField.THREAD_NAME],
                EventField.PREVIOUS_EVENT_ID: (
                    str(dict(r)[EventField.PREVIOUS_EVENT_ID])
                    if dict(r)[EventField.PREVIOUS_EVENT_ID] else None
                ),
            }
            for r in rows
        ],
    }
    await redis.set(key, json.dumps(result, default=str), ex=_TTL)
    return JSONResponse(result, headers={HttpHeader.X_CACHE: CacheStatus.MISS})
```

- [ ] **Step 4: Run — confirm PASS**

```bash
pytest tests/test_newsletters.py -v
```

Expected: 8 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/handlers/newsletters.py tests/test_newsletters.py
git commit -m "feat(newsletters): rewrite as async FastAPI router with asyncpg + redis.asyncio"
```

---

## Task 8: Rewrite src/handlers/subscriptions.py + tests

**Files:**
- Modify: `src/handlers/subscriptions.py`
- Modify: `tests/test_subscriptions.py`

- [ ] **Step 1: Write failing tests**

Replace `tests/test_subscriptions.py` entirely:

```python
import json
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fields import SubscriptionField, TopicField

_USER_ID = "test-user-sub"


def _make_client(pool: AsyncMock) -> TestClient:
    from handlers.subscriptions import router
    from dependencies import get_pool, get_user_id
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_user_id] = lambda: _USER_ID
    return TestClient(app)


def test_list_returns_subscriptions():
    pool = AsyncMock()
    pool.fetch.return_value = [
        {SubscriptionField.TOPIC_ID: "t-1", TopicField.NAME: "technology",
         SubscriptionField.SUBSCRIBED_AT: "2026-01-01T00:00:00+00:00"}
    ]
    resp = _make_client(pool).get("/subscriptions")
    assert resp.status_code == 200
    rows = resp.json()
    assert rows[0][TopicField.NAME] == "technology"


def test_post_subscribe_returns_201():
    pool = AsyncMock()
    pool.fetchrow.return_value = {
        SubscriptionField.TOPIC_ID: "t-1", TopicField.NAME: "technology",
        SubscriptionField.SUBSCRIBED_AT: "2026-01-01T00:00:00+00:00",
    }
    resp = _make_client(pool).post(
        "/subscriptions",
        json={SubscriptionField.TOPIC_ID: "t-1"},
    )
    assert resp.status_code == 201
    pool.fetchrow.assert_called_once()


def test_post_subscribe_returns_422_when_topic_id_missing():
    pool = AsyncMock()
    resp = _make_client(pool).post("/subscriptions", json={})
    assert resp.status_code == 422


def test_delete_returns_204():
    pool = AsyncMock()
    resp = _make_client(pool).delete("/subscriptions/t-1")
    assert resp.status_code == 204
    pool.execute.assert_called_once()


def test_list_returns_401_without_auth():
    from handlers.subscriptions import router
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app, raise_server_exceptions=False).get("/subscriptions")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run — confirm FAIL**

```bash
pytest tests/test_subscriptions.py -v
```

Expected: `ImportError` — no `router` attribute in old handler.

- [ ] **Step 3: Rewrite src/handlers/subscriptions.py**

```python
import asyncpg
from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dependencies import get_pool, get_user_id
from fields import SubscriptionField, TopicField

router = APIRouter()

_LIST_SQL = """
    SELECT s.topic_id, t.name, s.subscribed_at
    FROM subscriptions s JOIN topics t ON t.topic_id = s.topic_id
    WHERE s.user_id = $1 ORDER BY s.subscribed_at DESC
"""
_INSERT_SQL = """
    INSERT INTO subscriptions (user_id, topic_id) VALUES ($1, $2)
    ON CONFLICT (user_id, topic_id) DO NOTHING
    RETURNING topic_id,
        (SELECT name FROM topics WHERE topic_id = $2) AS name,
        subscribed_at
"""
_DELETE_SQL = "DELETE FROM subscriptions WHERE user_id = $1 AND topic_id = $2"


class SubscribeRequest(BaseModel):
    topic_id: str


@router.get("/subscriptions")
async def list_subscriptions(
    pool: asyncpg.Pool = Depends(get_pool),
    user_id: str = Depends(get_user_id),
):
    rows = await pool.fetch(_LIST_SQL, user_id)
    return JSONResponse([
        {
            **dict(r),
            SubscriptionField.TOPIC_ID: str(dict(r)[SubscriptionField.TOPIC_ID]),
            SubscriptionField.SUBSCRIBED_AT: str(dict(r)[SubscriptionField.SUBSCRIBED_AT]),
        }
        for r in rows
    ])


@router.post("/subscriptions", status_code=201)
async def subscribe(
    body: SubscribeRequest,
    pool: asyncpg.Pool = Depends(get_pool),
    user_id: str = Depends(get_user_id),
):
    row = await pool.fetchrow(_INSERT_SQL, user_id, body.topic_id)
    r = dict(row)
    return JSONResponse(
        {
            **r,
            SubscriptionField.TOPIC_ID: str(r[SubscriptionField.TOPIC_ID]),
            SubscriptionField.SUBSCRIBED_AT: str(r.get(SubscriptionField.SUBSCRIBED_AT, "")),
        },
        status_code=201,
    )


@router.delete("/subscriptions/{topic_id}", status_code=204)
async def unsubscribe(
    topic_id: str,
    pool: asyncpg.Pool = Depends(get_pool),
    user_id: str = Depends(get_user_id),
):
    await pool.execute(_DELETE_SQL, user_id, topic_id)
    return Response(status_code=204)
```

- [ ] **Step 4: Run — confirm PASS**

```bash
pytest tests/test_subscriptions.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v
```

- [ ] **Step 6: Commit**

```bash
git add src/handlers/subscriptions.py tests/test_subscriptions.py
git commit -m "feat(subscriptions): rewrite as async FastAPI router with Pydantic body"
```

---

## Task 9: Rewrite src/handlers/interactions.py + tests

**Files:**
- Modify: `src/handlers/interactions.py`
- Modify: `tests/test_interactions.py`

- [ ] **Step 1: Write failing tests**

Replace `tests/test_interactions.py` entirely:

```python
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fields import InteractionField, InteractionType

_USER_ID = "test-user-sub"


def _make_client(pool: AsyncMock) -> TestClient:
    from handlers.interactions import router
    from dependencies import get_pool, get_user_id
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_user_id] = lambda: _USER_ID
    return TestClient(app)


def test_post_records_interaction_and_returns_201():
    pool = AsyncMock()
    pool.fetchrow.return_value = {
        InteractionField.ID: "ix-1",
        InteractionField.CREATED_AT: "2026-04-24T00:00:00+00:00",
    }
    resp = _make_client(pool).post(
        "/interactions",
        json={InteractionField.EVENT_ID: "ev-001", InteractionField.TYPE: InteractionType.CLICK},
    )
    assert resp.status_code == 201
    pool.fetchrow.assert_called_once()


def test_post_returns_422_when_event_id_missing():
    pool = AsyncMock()
    resp = _make_client(pool).post(
        "/interactions",
        json={InteractionField.TYPE: InteractionType.CLICK},
    )
    assert resp.status_code == 422


def test_post_returns_422_when_type_invalid():
    pool = AsyncMock()
    resp = _make_client(pool).post(
        "/interactions",
        json={InteractionField.EVENT_ID: "ev-001", InteractionField.TYPE: "not_a_type"},
    )
    assert resp.status_code == 422


def test_post_accepts_all_valid_types():
    pool = AsyncMock()
    pool.fetchrow.return_value = {
        InteractionField.ID: "ix-1",
        InteractionField.CREATED_AT: "2026-04-24T00:00:00+00:00",
    }
    for t in InteractionType:
        resp = _make_client(pool).post(
            "/interactions",
            json={InteractionField.EVENT_ID: "ev-001", InteractionField.TYPE: t},
        )
        assert resp.status_code == 201, f"Expected 201 for type={t}"


def test_post_returns_401_without_auth():
    from handlers.interactions import router
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app, raise_server_exceptions=False).post("/interactions", json={})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run — confirm FAIL**

```bash
pytest tests/test_interactions.py -v
```

- [ ] **Step 3: Rewrite src/handlers/interactions.py**

```python
import asyncpg
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dependencies import get_pool, get_user_id
from fields import InteractionField, InteractionType

router = APIRouter()

_INSERT_SQL = """
    INSERT INTO interactions (user_id, event_id, type) VALUES ($1, $2, $3)
    RETURNING interaction_id, created_at
"""


class InteractionRequest(BaseModel):
    event_id: str
    type: InteractionType


@router.post("/interactions", status_code=201)
async def create_interaction(
    body: InteractionRequest,
    pool: asyncpg.Pool = Depends(get_pool),
    user_id: str = Depends(get_user_id),
):
    row = await pool.fetchrow(_INSERT_SQL, user_id, body.event_id, body.type)
    r = dict(row)
    return JSONResponse(
        {
            InteractionField.ID: str(r[InteractionField.ID]),
            InteractionField.CREATED_AT: str(r[InteractionField.CREATED_AT]),
        },
        status_code=201,
    )
```

- [ ] **Step 4: Run — confirm PASS**

```bash
pytest tests/test_interactions.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v
```

- [ ] **Step 6: Commit**

```bash
git add src/handlers/interactions.py tests/test_interactions.py
git commit -m "feat(interactions): rewrite as async FastAPI router with Pydantic validation"
```

---

## Task 10: Rewrite src/handlers/deep_dive.py + tests

**Files:**
- Modify: `src/handlers/deep_dive.py`
- Modify: `tests/test_deep_dive.py`

- [ ] **Step 1: Write failing tests**

Replace `tests/test_deep_dive.py` entirely:

```python
import json
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fields import DeepDiveField

_USER_ID = "test-user-sub"
_TEST_CHUNKS = ["chunk one", "chunk two"]


def _make_client(chunks=None, interval=0.0) -> TestClient:
    from handlers.deep_dive import router, get_deep_dive_chunks, get_chunk_interval
    from dependencies import get_user_id
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user_id] = lambda: _USER_ID
    if chunks is not None:
        app.dependency_overrides[get_deep_dive_chunks] = lambda: chunks
    app.dependency_overrides[get_chunk_interval] = lambda: interval
    return TestClient(app)


def test_deep_dive_returns_200_with_sse_content_type():
    resp = _make_client(_TEST_CHUNKS).post("/deep-dive/ev-001")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


def test_deep_dive_streams_chunks_in_order():
    resp = _make_client(_TEST_CHUNKS).post("/deep-dive/ev-001")
    lines = [ln for ln in resp.text.splitlines() if ln.startswith("data:")]
    payloads = [json.loads(ln[len("data: "):]) for ln in lines]
    chunks_received = [p[DeepDiveField.CHUNK] for p in payloads if not p[DeepDiveField.DONE]]
    assert chunks_received == _TEST_CHUNKS


def test_deep_dive_final_event_has_done_true():
    resp = _make_client(_TEST_CHUNKS).post("/deep-dive/ev-001")
    lines = [ln for ln in resp.text.splitlines() if ln.startswith("data:")]
    last = json.loads(lines[-1][len("data: "):])
    assert last[DeepDiveField.DONE] is True
    assert last[DeepDiveField.CHUNK] == ""


def test_deep_dive_uses_default_chunks_when_not_overridden():
    from handlers.deep_dive import router, get_chunk_interval, _DEFAULT_CHUNKS
    from dependencies import get_user_id
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user_id] = lambda: _USER_ID
    app.dependency_overrides[get_chunk_interval] = lambda: 0.0
    resp = TestClient(app).post("/deep-dive/ev-001")
    lines = [ln for ln in resp.text.splitlines() if ln.startswith("data:")]
    payloads = [json.loads(ln[len("data: "):]) for ln in lines]
    data_chunks = [p[DeepDiveField.CHUNK] for p in payloads if not p[DeepDiveField.DONE]]
    assert data_chunks == _DEFAULT_CHUNKS


def test_deep_dive_returns_401_without_auth():
    from handlers.deep_dive import router
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app, raise_server_exceptions=False).post("/deep-dive/ev-001")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run — confirm FAIL**

```bash
pytest tests/test_deep_dive.py -v
```

- [ ] **Step 3: Rewrite src/handlers/deep_dive.py**

```python
import asyncio
import json
import os

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from dependencies import get_user_id
from fields import DeepDiveField, EnvVar

router = APIRouter()

_DEFAULT_CHUNKS = [
    "This event marks a significant development in the ongoing story.",
    " Historical context: previous events in this thread laid the groundwork.",
    " Industry analysts expect broad adoption within the next quarter.",
    " Related threads suggest this will accelerate parallel developments.",
]


def get_deep_dive_chunks() -> list[str]:
    return _DEFAULT_CHUNKS


def get_chunk_interval() -> float:
    return float(os.environ.get(EnvVar.DEEP_DIVE_INTERVAL, "0.05"))


async def _sse_stream(chunks: list[str], interval: float):
    for chunk in chunks:
        yield f"data: {json.dumps({DeepDiveField.CHUNK: chunk, DeepDiveField.DONE: False})}\n\n"
        await asyncio.sleep(interval)
    yield f"data: {json.dumps({DeepDiveField.CHUNK: '', DeepDiveField.DONE: True})}\n\n"


@router.post("/deep-dive/{event_id}")
async def deep_dive(
    event_id: str,
    user_id: str = Depends(get_user_id),
    chunks: list[str] = Depends(get_deep_dive_chunks),
    interval: float = Depends(get_chunk_interval),
):
    return StreamingResponse(
        _sse_stream(chunks, interval),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 4: Run — confirm PASS**

```bash
pytest tests/test_deep_dive.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v
```

- [ ] **Step 6: Commit**

```bash
git add src/handlers/deep_dive.py tests/test_deep_dive.py
git commit -m "feat(deep-dive): rewrite as async FastAPI StreamingResponse with parametric SSE"
```

---

## Task 11: src/main.py + tests/test_main.py

**Files:**
- Create: `src/main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_main.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client(mock_pool, mock_redis):
    with patch("db_async.create_pool", return_value=mock_pool), \
         patch("cache_async.create_redis", return_value=mock_redis):
        from main import app
        with TestClient(app) as c:
            yield c


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_body(client):
    resp = client.get("/health")
    assert resp.json() == {"status": "ok"}


def test_health_does_not_require_auth(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_newsletters_route_registered(client, mock_pool, mock_redis):
    from dependencies import get_pool, get_redis, get_user_id
    from main import app
    app.dependency_overrides[get_pool] = lambda: mock_pool
    app.dependency_overrides[get_redis] = lambda: mock_redis
    app.dependency_overrides[get_user_id] = lambda: "u-1"
    mock_redis.get.return_value = "[]"
    resp = client.get("/newsletters")
    assert resp.status_code == 200
    app.dependency_overrides.clear()


def test_interactions_route_registered(client):
    from dependencies import get_pool, get_user_id
    from main import app
    pool = AsyncMock()
    pool.fetchrow.return_value = {"interaction_id": "ix-1", "created_at": "2026-01-01"}
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_user_id] = lambda: "u-1"
    resp = client.post("/interactions", json={"event_id": "ev-1", "type": "view"})
    assert resp.status_code == 201
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run — confirm FAIL**

```bash
pytest tests/test_main.py -v
```

Expected: `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Create src/main.py**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

import cache_async
import db_async
from handlers import deep_dive, interactions, newsletters, subscriptions


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await db_async.create_pool()
    app.state.redis = await cache_async.create_redis()
    yield
    await app.state.pool.close()
    await app.state.redis.aclose()


app = FastAPI(lifespan=lifespan)

app.include_router(newsletters.router)
app.include_router(subscriptions.router)
app.include_router(interactions.router)
app.include_router(deep_dive.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Run — confirm PASS**

```bash
pytest tests/test_main.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat(main): FastAPI app with lifespan, router registration, /health endpoint"
```

---

## Task 12: Terraform fargate module

**Files:**
- Create: `terraform/modules/fargate/main.tf`
- Create: `terraform/modules/fargate/variables.tf`
- Create: `terraform/modules/fargate/outputs.tf`

- [ ] **Step 1: Create terraform/modules/fargate/variables.tf**

```hcl
variable "name_prefix" {
  type    = string
  default = "newsletter"
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "aurora_sg_id" {
  type        = string
  description = "Existing aurora SG — fargate module adds an ingress rule to it"
}

variable "redis_sg_id" {
  type        = string
  description = "Existing redis SG — fargate module adds an ingress rule to it"
}

variable "aurora_secret_arn" {
  type        = string
  description = "Secrets Manager ARN for DB password (injected into container)"
}

variable "db_host" {
  type = string
}

variable "db_name" {
  type    = string
  default = "newsletter"
}

variable "db_user" {
  type    = string
  default = "newsletter"
}

variable "redis_endpoint" {
  type = string
}

variable "cognito_user_pool_id" {
  type        = string
  description = "SAM-managed Cognito User Pool ID for JWT verification"
}

variable "region" {
  type    = string
  default = "eu-west-1"
}

variable "uvicorn_workers" {
  type        = number
  default     = 1
  description = "Uvicorn worker count. Free tier: 1 (max 40 DB conns). Premium (Aurora+Proxy): 3."
}

variable "image_tag" {
  type    = string
  default = "latest"
}
```

- [ ] **Step 2: Create terraform/modules/fargate/main.tf**

```hcl
resource "aws_ecr_repository" "main" {
  name         = "${var.name_prefix}-newsletter"
  force_delete = true
}

resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"
}

resource "aws_cloudwatch_log_group" "main" {
  name              = "/ecs/${var.name_prefix}-newsletter"
  retention_in_days = 7
}

resource "aws_iam_role" "execution" {
  name = "${var.name_prefix}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secrets" {
  name = "${var.name_prefix}-ecs-secrets"
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [var.aurora_secret_arn]
    }]
  })
}

# ALB security group — all rules inline (no SG references)
resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb-sg"
  description = "ALB: ingress 80 from internet, egress all"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Fargate security group — no inline rules, all via aws_security_group_rule below
resource "aws_security_group" "fargate" {
  name        = "${var.name_prefix}-fargate-sg"
  description = "Fargate tasks"
  vpc_id      = var.vpc_id
}

resource "aws_security_group_rule" "fargate_ingress_alb" {
  type                     = "ingress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.fargate.id
  source_security_group_id = aws_security_group.alb.id
}

resource "aws_security_group_rule" "fargate_egress_https" {
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.fargate.id
}

resource "aws_security_group_rule" "fargate_egress_aurora" {
  type                     = "egress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.fargate.id
  source_security_group_id = var.aurora_sg_id
}

resource "aws_security_group_rule" "fargate_egress_redis" {
  type                     = "egress"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  security_group_id        = aws_security_group.fargate.id
  source_security_group_id = var.redis_sg_id
}

# Allow Fargate → Aurora (adds rule to existing aurora SG)
resource "aws_security_group_rule" "aurora_ingress_fargate" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = var.aurora_sg_id
  source_security_group_id = aws_security_group.fargate.id
}

# Allow Fargate → Redis (adds rule to existing redis SG)
resource "aws_security_group_rule" "redis_ingress_fargate" {
  type                     = "ingress"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  security_group_id        = var.redis_sg_id
  source_security_group_id = aws_security_group.fargate.id
}

resource "aws_lb" "main" {
  name               = "${var.name_prefix}-alb"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids
  internal           = false
}

resource "aws_lb_target_group" "main" {
  name        = "${var.name_prefix}-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    interval            = 30
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "main" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.main.arn
  }
}

resource "aws_ecs_task_definition" "main" {
  family                   = "${var.name_prefix}-newsletter"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.execution.arn

  container_definitions = jsonencode([{
    name  = "newsletter"
    image = "${aws_ecr_repository.main.repository_url}:${var.image_tag}"
    portMappings = [{ containerPort = 8000, hostPort = 8000, protocol = "tcp" }]
    environment = [
      { name = "DB_HOST",              value = var.db_host },
      { name = "DB_NAME",              value = var.db_name },
      { name = "DB_USER",              value = var.db_user },
      { name = "REDIS_HOST",           value = var.redis_endpoint },
      { name = "REDIS_SSL",            value = "true" },
      { name = "COGNITO_USER_POOL_ID", value = var.cognito_user_pool_id },
      { name = "AWS_REGION",           value = var.region },
      { name = "DEEP_DIVE_INTERVAL",   value = "0.05" },
      { name = "UVICORN_WORKERS",      value = tostring(var.uvicorn_workers) },
    ]
    secrets = [
      { name = "DB_PASSWORD", valueFrom = var.aurora_secret_arn }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.main.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
}

resource "aws_ecs_service" "main" {
  name            = "${var.name_prefix}-newsletter-svc"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.main.arn
  desired_count   = 0
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.fargate.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.main.arn
    container_name   = "newsletter"
    container_port   = 8000
  }

  # Autoscaler manages desired_count; task_definition pin managed by deploy step
  lifecycle {
    ignore_changes = [desired_count, task_definition]
  }

  depends_on = [aws_lb_listener.main]
}

resource "aws_appautoscaling_target" "main" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.main.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = 0
  max_capacity       = 2

  depends_on = [aws_ecs_service.main]
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "${var.name_prefix}-cpu-scaling"
  service_namespace  = "ecs"
  resource_id        = aws_appautoscaling_target.main.resource_id
  scalable_dimension = aws_appautoscaling_target.main.scalable_dimension
  policy_type        = "TargetTrackingScaling"

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# TODO (post-benchmark): add ALBRequestCountPerTarget policy
# After running load_tests/capacity_benchmark.js:
#   1. Find last VU stage where p99 < 100ms AND error_rate < 0.1% → note req/s as S
#   2. Threshold = S × 60 × 0.7  (req/min per target, 30% safety margin)
#   3. Add aws_appautoscaling_policy "alb_req_count" with predefined_metric_type =
#      "ALBRequestCountPerTarget" and target_value = threshold
#   4. terraform apply
```

- [ ] **Step 3: Create terraform/modules/fargate/outputs.tf**

```hcl
output "alb_dns" {
  value = aws_lb.main.dns_name
}

output "ecr_repo_url" {
  value = aws_ecr_repository.main.repository_url
}

output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "service_name" {
  value = aws_ecs_service.main.name
}
```

- [ ] **Step 4: Validate Terraform syntax**

```bash
cd terraform/modules/fargate
terraform init -backend=false
terraform validate
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 5: Commit**

```bash
git add terraform/modules/fargate/
git commit -m "infra(fargate): add Fargate module — ECS, ALB, ECR, auto-scaling, SG rules"
```

---

## Task 13: Extend terraform/envs/dev/

**Files:**
- Modify: `terraform/envs/dev/main.tf`
- Modify: `terraform/envs/dev/variables.tf`
- Modify: `terraform/envs/dev/outputs.tf`

- [ ] **Step 1: Add fargate module block to terraform/envs/dev/main.tf**

Add after the existing `module "bastion"` block:

```hcl
module "fargate" {
  source               = "../../modules/fargate"
  name_prefix          = var.name_prefix
  vpc_id               = module.vpc.vpc_id
  public_subnet_ids    = module.vpc.public_subnet_ids
  private_subnet_ids   = module.vpc.private_subnet_ids
  aurora_sg_id         = module.vpc.aurora_sg_id
  redis_sg_id          = module.vpc.redis_sg_id
  aurora_secret_arn    = module.aurora.secret_arn
  db_host              = module.aurora.cluster_endpoint
  db_name              = var.db_name
  db_user              = var.db_user
  redis_endpoint       = module.redis.redis_endpoint
  cognito_user_pool_id = var.cognito_user_pool_id
  region               = var.region
  uvicorn_workers      = var.fargate_uvicorn_workers
}
```

- [ ] **Step 2: Add variables to terraform/envs/dev/variables.tf**

Append to the end of the file:

```hcl
variable "cognito_user_pool_id" {
  type        = string
  description = "SAM-managed Cognito User Pool ID (from aws cognito-idp list-user-pools)"
}

variable "fargate_uvicorn_workers" {
  type        = number
  default     = 1
  description = "Uvicorn workers per task. Free tier: 1. Premium (Aurora+Proxy): 3."
}
```

- [ ] **Step 3: Add outputs to terraform/envs/dev/outputs.tf**

Append to the end of the file:

```hcl
output "alb_dns" {
  value = module.fargate.alb_dns
}

output "ecr_repo_url" {
  value = module.fargate.ecr_repo_url
}

output "ecs_cluster" {
  value = module.fargate.cluster_name
}

output "ecs_service" {
  value = module.fargate.service_name
}
```

- [ ] **Step 4: Validate Terraform syntax**

```bash
cd terraform/envs/dev
terraform validate
```

Expected: `Success! The configuration is valid.`
(If `cognito_user_pool_id` has no default, provide it: `terraform validate -var="cognito_user_pool_id=eu-west-1_EU46ArwA7"`)

- [ ] **Step 5: Add example tfvars entry**

In `terraform/envs/dev/terraform.tfvars.example`, add:

```
cognito_user_pool_id  = "eu-west-1_EU46ArwA7"
fargate_uvicorn_workers = 1
```

- [ ] **Step 6: Commit**

```bash
git add terraform/envs/dev/main.tf terraform/envs/dev/variables.tf terraform/envs/dev/outputs.tf terraform/envs/dev/terraform.tfvars.example
git commit -m "infra(dev): wire fargate module into dev env with cognito_user_pool_id var"
```

---

## Task 14: Update k6 load test thresholds + add capacity_benchmark.js

**Files:**
- Modify: `load_tests/newsletter_uncached.js`
- Modify: `load_tests/mixed_realistic.js`
- Modify: `load_tests/deep_dive_sse.js`
- Create: `load_tests/capacity_benchmark.js`

- [ ] **Step 1: Tighten newsletter_uncached.js threshold**

In `load_tests/newsletter_uncached.js`, change line:

```js
"http_req_duration{scenario:load}": ["p(99)<300"],
```

to:

```js
"http_req_duration{scenario:load}": ["p(99)<100"],
```

- [ ] **Step 2: Tighten mixed_realistic.js threshold**

In `load_tests/mixed_realistic.js`, change line:

```js
http_req_duration: ["p(95)<200"],
```

to:

```js
http_req_duration: ["p(95)<150"],
```

- [ ] **Step 3: Tighten deep_dive_sse.js threshold**

In `load_tests/deep_dive_sse.js`, change line:

```js
thresholds: { http_req_duration: ["p(95)<5000"], http_req_failed: ["rate<0.01"] },
```

to:

```js
thresholds: { http_req_duration: ["p(95)<500"], http_req_failed: ["rate<0.01"] },
```

(Full SSE stream at 4 chunks × 50ms = 200ms + network, so p95 < 500ms is appropriate.)

- [ ] **Step 4: Create load_tests/capacity_benchmark.js**

```js
import http from "k6/http";
import { check } from "k6";
import { BASE_URL, headers, NEWSLETTER_IDS } from "./config.js";

// Stepped VU ramp — observation only, no pass/fail thresholds.
// After running, inspect k6 output per stage:
//   1. Find last stage where p99 < 100ms AND error_rate < 0.1% → this is your safe req/s (S)
//   2. Note CPU% from CloudWatch ECS metrics at that stage
//   3. Optional: set ALBRequestCountPerTarget threshold = S × 60 × 0.7 in Terraform
//   4. Update aws_appautoscaling_policy.cpu target_value to observed CPU% if different from 70
export const options = {
  stages: [
    { duration: "2m", target: 10 },
    { duration: "2m", target: 25 },
    { duration: "2m", target: 50 },
    { duration: "2m", target: 100 },
    { duration: "2m", target: 150 },
    { duration: "2m", target: 200 },
    { duration: "1m", target: 0 },
  ],
};

export default function () {
  const id = NEWSLETTER_IDS[Math.floor(Math.random() * NEWSLETTER_IDS.length)];
  const res = http.get(`${BASE_URL}/newsletters/${id}`, { headers });
  check(res, { "200": (r) => r.status === 200 });
}
```

- [ ] **Step 5: Commit**

```bash
git add load_tests/newsletter_uncached.js load_tests/mixed_realistic.js load_tests/deep_dive_sse.js load_tests/capacity_benchmark.js
git commit -m "test(load): tighten Fargate thresholds + add capacity_benchmark.js"
```

---

## Task 15: Pipeline extensions (steps, paths, pipeline, scale scripts)

**Files:**
- Modify: `scripts/steps.py`
- Modify: `scripts/paths.py`
- Modify: `scripts/pipeline.py`
- Create: `scripts/scale_up.py`
- Create: `scripts/scale_down.py`
- Create: `scripts/deploy_fargate.sh`
- Modify: `config/dev.yaml`

- [ ] **Step 1: Extend scripts/steps.py**

Replace `scripts/steps.py` entirely:

```python
from enum import StrEnum

LOAD_TEST_DIR = "load_tests"


class Step(StrEnum):
    # Lambda pipeline steps (unchanged)
    SEED     = "seed"
    TOKENS   = "tokens"
    IDS      = "ids"
    SMOKE    = "smoke"
    FLUSH    = "flush"
    UNCACHED = "uncached"
    PREWARM  = "prewarm"
    CACHED   = "cached"
    SSE      = "sse"
    MIXED    = "mixed"
    STRESS   = "stress"
    # Fargate-only steps
    DEPLOY     = "deploy"
    SCALE_UP   = "scale_up"
    BENCHMARK  = "benchmark"
    SCALE_DOWN = "scale_down"


STEP_ORDER: list[Step] = [
    Step.SEED, Step.TOKENS, Step.IDS,
    Step.SMOKE, Step.FLUSH, Step.UNCACHED, Step.PREWARM,
    Step.CACHED, Step.SSE, Step.MIXED, Step.STRESS,
]

FARGATE_STEP_ORDER: list[Step] = [
    Step.DEPLOY, Step.SCALE_UP,
    Step.SEED, Step.TOKENS, Step.IDS,
    Step.SMOKE, Step.FLUSH, Step.UNCACHED, Step.PREWARM,
    Step.CACHED, Step.SSE, Step.MIXED, Step.BENCHMARK,
    Step.SCALE_DOWN,
]

K6_SCRIPTS: dict[Step, tuple[str, str]] = {
    Step.SMOKE:     ("smoke.js",               "1 VU · sanity check"),
    Step.UNCACHED:  ("newsletter_uncached.js",  "30s warmup → 200 VUs · p99<100ms"),
    Step.CACHED:    ("newsletter_cached.js",    "500 VUs · p99<50ms"),
    Step.SSE:       ("deep_dive_sse.js",        "50 VUs · p95<500ms"),
    Step.MIXED:     ("mixed_realistic.js",      "1000 VUs · p95<150ms"),
    Step.STRESS:    ("cold_start_stress.js",    "spike 0→1000 VUs · errors<1%"),
    Step.BENCHMARK: ("capacity_benchmark.js",   "stepped ramp · observation only"),
}

DB_STEPS: set[Step] = {Step.SEED, Step.IDS}
```

- [ ] **Step 2: Extend scripts/paths.py**

Append to `scripts/paths.py`:

```python
DEPLOY_FARGATE_SCRIPT = SCRIPTS_DIR / "deploy_fargate.sh"
SCALE_UP_SCRIPT       = SCRIPTS_DIR / "scale_up.py"
SCALE_DOWN_SCRIPT     = SCRIPTS_DIR / "scale_down.py"
```

- [ ] **Step 3: Create scripts/scale_up.py**

```python
#!/usr/bin/env python3
"""Set ECS service desired_count=2 and poll until 2 tasks are RUNNING (max 120s)."""
import json
import os
import subprocess
import sys
import time


def _aws(args: list[str]) -> dict:
    r = subprocess.run(
        ["aws"] + args + ["--output", "json"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(r.stdout)


def main() -> None:
    cluster = os.environ["ECS_CLUSTER"]
    service = os.environ["ECS_SERVICE"]
    region  = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
    base    = ["--region", region]

    subprocess.run(
        ["aws", "ecs", "update-service",
         "--cluster", cluster, "--service", service,
         "--desired-count", "2"] + base,
        check=True, capture_output=True,
    )
    print("Scaling to 2 tasks — waiting for RUNNING state...", file=sys.stderr)

    deadline = time.time() + 120
    while time.time() < deadline:
        data    = _aws(["ecs", "describe-services",
                        "--cluster", cluster, "--services", service] + base)
        running = data["services"][0]["runningCount"]
        print(f"  running: {running}/2", file=sys.stderr)
        if running >= 2:
            print("Tasks ready.", file=sys.stderr)
            return
        time.sleep(10)

    sys.exit("Timeout: fewer than 2 tasks RUNNING after 120s")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create scripts/scale_down.py**

```python
#!/usr/bin/env python3
"""Set ECS service desired_count=0."""
import os
import subprocess
import sys


def main() -> None:
    cluster = os.environ["ECS_CLUSTER"]
    service = os.environ["ECS_SERVICE"]
    region  = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")

    subprocess.run(
        ["aws", "ecs", "update-service",
         "--cluster", cluster, "--service", service,
         "--desired-count", "0",
         "--region", region],
        check=True, capture_output=True,
    )
    print("Service scaled to 0.", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Create scripts/deploy_fargate.sh**

```bash
#!/usr/bin/env bash
# Build Docker image, push to ECR, force ECS service redeployment.
# Required env vars: ECR_REPO_URL, ECS_CLUSTER, ECS_SERVICE
# Optional: AWS_DEFAULT_REGION (default: eu-west-1)
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-eu-west-1}"
REPO="${ECR_REPO_URL:?ECR_REPO_URL is required}"
CLUSTER="${ECS_CLUSTER:?ECS_CLUSTER is required}"
SERVICE="${ECS_SERVICE:?ECS_SERVICE is required}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== ECR login ===" >&2
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${REPO%%/*}"

echo "=== docker build ===" >&2
docker build -t newsletter:latest "$ROOT_DIR"

echo "=== docker tag + push ===" >&2
docker tag newsletter:latest "$REPO:latest"
docker push "$REPO:latest"

echo "=== force ECS redeployment ===" >&2
aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --force-new-deployment \
  --region "$REGION" \
  --output json > /dev/null

echo "Deploy triggered. Tasks will cycle with new image." >&2
```

- [ ] **Step 6: Rewrite scripts/pipeline.py**

Replace `scripts/pipeline.py` entirely:

```python
#!/usr/bin/env python3
"""
Full load-test pipeline. Supports --runtime lambda (default) and --runtime fargate.

Lambda steps:   seed → tokens → ids → smoke → flush → uncached → prewarm → cached → sse → mixed → stress
Fargate steps:  deploy → scale_up → seed → tokens → ids → smoke → flush → uncached → prewarm
                → cached → sse → mixed → benchmark → scale_down

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
    DEPLOY_FARGATE_SCRIPT, SCALE_UP_SCRIPT, SCALE_DOWN_SCRIPT,
    get_out_filepath, OutFile,
)
from tunnel import ssm_tunnel, Service          # noqa: E402
from utils import timed, die                   # noqa: E402
from models import SeedResult                  # noqa: E402
from steps import Step, STEP_ORDER, FARGATE_STEP_ORDER, K6_SCRIPTS, DB_STEPS  # noqa: E402
from run_load_tests import run_k6, preflight_k6  # noqa: E402


def run_script(script: pathlib.Path, env: dict, extra: list[str] | None = None) -> None:
    cmd = [sys.executable, str(script)] + (extra or [])
    print(f"\n=== {script.name} ===", file=sys.stderr)
    with timed(script.name):
        r = subprocess.run(cmd, env=env)
    if r.returncode != 0:
        die(f"{script.name} failed (exit {r.returncode})")


def run_shell(script: pathlib.Path, env: dict) -> None:
    print(f"\n=== {script.name} ===", file=sys.stderr)
    with timed(script.name):
        r = subprocess.run(["bash", str(script)], env=env)
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
    runtime: str, db_env: dict, k6_vars: dict[str, str], _env: str
) -> dict[Step, Callable[[], None]]:
    runners: dict[Step, Callable[[], None]] = {
        Step.SEED:    lambda: run_script(SEED_SCRIPT, db_env),
        Step.TOKENS:  lambda: run_script(TOKENS_SCRIPT, os.environ),
        Step.IDS:     lambda: run_script(IDS_SCRIPT, db_env, ["--count", str(_ids_count(_env))]),
        Step.FLUSH:   lambda: run_script(FLUSH_SCRIPT, os.environ),
        Step.PREWARM: lambda: run_script(PREWARM_SCRIPT, os.environ),
    }
    for step in K6_SCRIPTS:
        runners[step] = lambda s=step: run_k6(s, k6_vars)

    if runtime == "fargate":
        runners[Step.DEPLOY]     = lambda: run_shell(DEPLOY_FARGATE_SCRIPT, os.environ)
        runners[Step.SCALE_UP]   = lambda: run_script(SCALE_UP_SCRIPT, os.environ)
        runners[Step.SCALE_DOWN] = lambda: run_script(SCALE_DOWN_SCRIPT, os.environ)

    return runners


def _run_pipeline_steps(steps: list[Step], runners: dict[Step, Callable[[], None]]) -> None:
    for step in steps:
        runners[step]()


def run_pipeline(steps: list[Step], runtime: str, db_env: dict, _env: str) -> None:
    k6_vars = preflight_k6(steps, _env)
    runners = _build_runners(runtime, db_env, k6_vars, _env)

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
```

- [ ] **Step 7: Add fargate.alb_url key to config/dev.yaml**

Add under the `api:` section (fill in after `terraform apply`):

```yaml
fargate:
  alb_url: ""   # fill after: terraform -chdir=terraform/envs/dev output -raw alb_dns
```

- [ ] **Step 8: Verify pipeline imports are clean**

```bash
cd scripts && python -c "from pipeline import run_pipeline; print('OK')"
```

Expected: `OK`

- [ ] **Step 9: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
git add scripts/steps.py scripts/paths.py scripts/pipeline.py scripts/scale_up.py scripts/scale_down.py scripts/deploy_fargate.sh config/dev.yaml
git commit -m "feat(pipeline): add Fargate runtime with deploy/scale_up/benchmark/scale_down steps"
```

---

## Self-Review

### Spec coverage check

| Spec section | Covered by task |
|---|---|
| Section 1 — Architecture (asyncpg pool, no RDS Proxy, free tier) | Task 4 (db_async.py) |
| Section 2 — main.py lifespan | Task 11 |
| Section 2 — dependency injection | Task 5 |
| Section 2 — newsletters router | Task 7 |
| Section 2 — subscriptions router | Task 8 |
| Section 2 — interactions router + Pydantic | Task 9 |
| Section 2 — deep-dive parametric SSE | Task 10 |
| Section 2 — auth.py JWKS+RS256 | Task 3 |
| Section 2 — Dockerfile | Task 2 |
| Section 2 — requirements-fargate.txt | Task 2 |
| Section 3 — fargate Terraform module | Task 12 |
| Section 3 — dev env wiring | Task 13 |
| Section 3 — auto-scaling CPU 70% | Task 12 (aws_appautoscaling_policy.cpu) |
| Section 3 — scale-to-zero (desired_count=0) | Task 12 (aws_ecs_service) |
| Section 4 — test fixtures (mock_pool, mock_redis) | Task 6 |
| Section 4 — handler coverage (cache hit/miss, 404, 422, 401) | Tasks 7-10 |
| Section 4 — SSE parametric override | Task 10 |
| Section 5 — FARGATE_STEP_ORDER | Task 15 |
| Section 5 — --runtime flag | Task 15 |
| Section 5 — scale_down in finally | Task 15 |
| Section 5 — capacity_benchmark.js | Task 14 |
| Section 6 — tightened thresholds | Task 14 |
| Section 6 — cold_start replaced by benchmark | Task 14 (benchmark added) |
| fields.py env vars | Task 1 |

### Placeholder scan

No TBDs, no "implement later" patterns. All code blocks complete.

### Type consistency check

- `get_pool` returns `asyncpg.Pool` — used consistently in Tasks 7, 8, 9 as `pool: asyncpg.Pool = Depends(get_pool)`
- `get_redis` returns `aioredis.Redis` — used in Tasks 7, 8 as `redis=Depends(get_redis)`
- `get_user_id` returns `str` — used in Tasks 7–10 as `user_id: str = Depends(get_user_id)`
- `get_deep_dive_chunks` returns `list[str]` — used in Task 10 as `chunks: list[str] = Depends(get_deep_dive_chunks)`
- `get_chunk_interval` returns `float` — used in Task 10 as `interval: float = Depends(get_chunk_interval)`
- `_DEFAULT_CHUNKS` referenced in test `test_deep_dive_uses_default_chunks_when_not_overridden` — exported from `handlers/deep_dive.py` ✓
- `auth._jwks` (lru_cache'd function) cleared with `auth._jwks.cache_clear()` in tests ✓

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-13-fargate-serving-layer.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
