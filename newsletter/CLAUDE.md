# CLAUDE.md — newsletter (Python/FastAPI)

App-specific guidance. Repo-wide rules in root `CLAUDE.md`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12, ECS Fargate |
| Web framework | FastAPI + uvicorn (1 vCPU / 2 GB per task, max 2 tasks) |
| API | ALB (port 80) + FastAPI JWT middleware (python-jose, RS256) |
| DB driver | asyncpg (async pool, max 20 conns) |
| Cache driver | redis.asyncio |
| Cache | ElastiCache Serverless (Redis), TTL 1h |
| Database | RDS PostgreSQL db.t3.micro (direct; RDS Proxy on premium plan) |
| IaC | Terraform (`terraform/modules/fargate/`); SAM kept in `infra/` for reference |
| Local dev | Docker Compose (PostgreSQL + Redis) |
| Testing | pytest, pytest-mock, FastAPI TestClient |
| Load testing | k6 |

---

## File Structure

```
newsletter/
  src/
    main.py                  # FastAPI app, lifespan, router registration
    auth.py                  # JWT: JWKS fetch (cached), RS256 verify, 401 on failure
    dependencies.py          # get_pool(), get_redis(), get_user_id() — Depends providers
    db_async.py              # asyncpg pool factory
    cache_async.py           # redis.asyncio client factory
    fields.py                # StrEnum constants
    response.py              # HTTP response builders
    db.py                    # psycopg2 sync client (Lambda backward compat, kept)
    cache.py                 # redis-py sync client (Lambda backward compat, kept)
    handlers/
      newsletters.py         # async FastAPI router — GET /newsletters, GET /newsletters/{id}
      subscriptions.py       # async FastAPI router — GET/POST/DELETE /subscriptions
      interactions.py        # async FastAPI router — POST /interactions
      deep_dive.py           # StreamingResponse + SSE generator — POST /deep-dive/{event_id}
  tests/
    conftest.py              # client, mock_pool fixtures (FastAPI TestClient)
  scripts/
    00_seed.py               # Truncate → insert mock data → pre-warm Redis
    01_prewarm.py            # Pre-warm Redis from seed result
    02_create_test_tokens.py # Issue 100 Cognito Bearer tokens for load tests
    03_get_load_test_ids.py  # Query live DB for newsletter/event IDs
    flush_redis.py           # Flush all Redis keys (cold-start scenarios)
    pipeline.py              # Full load-test pipeline orchestrator
    run_load_tests.py        # k6 runner — reads tokens/IDs, runs scenarios
    scale_up.py              # Set ECS desired_count=2
    scale_down.py            # Set ECS desired_count=0
    config.py / models.py / paths.py / steps.py / tunnel.py / utils.py
    out/                     # Generated: seed results, tokens, IDs
  pytest.ini
  pyrightconfig.json
  requirements.txt / requirements-dev.txt / requirements-fargate.txt
  Dockerfile
```

---

## Validation — Run After Every Code Change

```bash
# Unit tests (no network required — uses mock_db / mock_cache fixtures)
cd newsletter && pytest tests/ -v

# Type check (if mypy is added later)
# mypy src/

# Lint
# ruff check src/ tests/
```

All tests must pass before committing. Zero failures is the bar — no skips allowed unless the test is explicitly marked `@pytest.mark.skip(reason="...")` with a reason.

---

## Coding Standards

### Handler shape — FastAPI routers

Every handler file exposes an `APIRouter`. Routes use dependency injection — never extract auth or connections manually.

```python
# handlers/newsletters.py
router = APIRouter()

@router.get("/newsletters/{newsletter_id}")
async def get_newsletter(
    newsletter_id: str,
    pool: asyncpg.Pool = Depends(get_pool),
    redis = Depends(get_redis),
    user_id: str = Depends(get_user_id),
):
    ...
```

`user_id` comes exclusively from `Depends(get_user_id)` → `auth.verify(token)`. Never accept it as a query or body parameter.

### Testability — dependency overrides

Tests override dependencies via `app.dependency_overrides`, not `mocker.patch`.

```python
# CORRECT
app.dependency_overrides[get_pool] = lambda: mock_pool
app.dependency_overrides[get_user_id] = lambda: "test-user-sub"

# WRONG — patching import names has no effect with FastAPI DI
mocker.patch("db_async.create_pool")
```

### Response builders

Use only `src/response.py` helpers — never construct raw dicts inline:

```python
from response import ok, created, not_found, bad_request, server_error
```

### String constants — use `StrEnum`

Never hardcode any string key as a literal. Use `StrEnum` classes from `src/fields.py` instead. Values compare equal to plain strings, so dict access, f-strings, and comparisons work unchanged.

```python
# CORRECT
from fields import NewsletterField, CachePrefix, InteractionType, LambdaEvent, LambdaResponse, HttpMethod

event[LambdaEvent.HTTP_METHOD] == HttpMethod.GET          # "httpMethod" / "GET"
event[LambdaEvent.PATH_PARAMETERS][NewsletterField.ID]    # path param "newsletter_id"
f"{CachePrefix.NEWSLETTER}{newsletter_id}"                # "newsletter:{id}"
resp[LambdaResponse.STATUS_CODE]                          # "statusCode"
if body[InteractionField.TYPE] not in list(InteractionType):

# WRONG — magic strings
event["httpMethod"] == "GET"
event["pathParameters"]["newsletter_id"]
resp["statusCode"]
```

**What belongs in `src/fields.py`:**

| Class | Covers |
|---|---|
| `LambdaEvent` | Incoming event keys: `httpMethod`, `resource`, `pathParameters`, `requestContext`, `body`, `headers`, `authorizer`, `claims`, `sub` |
| `LambdaResponse` | Outgoing response keys: `statusCode`, `headers`, `body` |
| `HttpMethod` | HTTP method values: `GET`, `POST`, `DELETE` |
| `HttpHeader` | Header names: `Content-Type`, `Cache-Control`, etc. |
| `ContentType` | Header values: `application/json`, `text/event-stream` |
| `EnvVar` | Environment variable names: `DB_HOST`, `REDIS_HOST`, etc. |
| Domain field classes | DB column names, response payload keys, cache key prefixes, interaction types, SSE field names |

**Adding new fields:** extend the relevant `StrEnum` class in `src/fields.py` before using the string anywhere else.

### No comments on obvious code

Only add a comment when the **why** is non-obvious (hidden constraint, workaround, subtle invariant). Never describe what the code does.

---

## Testing Standards

### TDD — test before implementation

1. Write the failing test
2. Run it — confirm it fails with the expected error
3. Write minimal implementation
4. Run again — confirm it passes
5. Commit

### Fixture usage

```python
# tests/conftest.py provides:
# mock_pool   → (pool, conn) AsyncMock pair; conn.fetchrow / conn.fetch return values
# client      → FastAPI TestClient with get_pool / get_redis / get_user_id overridden

def test_get_newsletter_cache_hit(client, mock_pool):
    _, conn = mock_pool
    # Redis hit: dependency_overrides[get_redis] returns AsyncMock with .get() → JSON string
    response = client.get("/newsletters/abc")
    assert response.status_code == 200
    conn.fetchrow.assert_not_called()   # Aurora not touched on cache hit
```

### What to test per handler

- Cache hit → Aurora not called
- Cache miss → Aurora called, result cached
- Aurora returns empty → 404
- Missing required body fields → 400
- Happy path → correct status code + response shape

---

## Non-Regression Checklist

Before marking any task complete:

```bash
# 1. Full test suite
cd newsletter && pytest tests/ -v

# 2. No new test skips introduced
cd newsletter && pytest tests/ -v | grep -i skip   # must be empty (or same as before)

# 3. Docker Compose is up for integration smoke (optional, manual)
docker-compose up -d
# run seed.py locally if schema changed
# docker-compose down
```

### Load test pass criteria (Phase 1 gate)

| Scenario | Tool | Command |
|---|---|---|---|
| Newsletter cached | k6 | `k6 run load_tests/newsletter_cached.js` |
| Newsletter uncached | k6 | `k6 run load_tests/newsletter_uncached.js` |
| Mixed realistic | k6 | `k6 run load_tests/mixed_realistic.js` |
| Deep-dive SSE | k6 | `k6 run load_tests/deep_dive_sse.js` |
| Capacity benchmark | k6 | `k6 run load_tests/capacity_benchmark.js` |

All four gated scenarios must pass before real data integration begins. Capacity benchmark is run for auto-scaling calibration only.
