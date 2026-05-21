# CLAUDE.md

Guidance for Claude Code when working in this repository.

---

## Project Overview

AWS-native newsletter platform. Currently building the **API / Serving Layer** (Phase 1) with mocked data for load testing. Real NLP/LLM pipeline is out of scope until load tests pass.

**Original spec:** `docs/superpowers/specs/2026-04-23-api-serving-layer-design.md`
**Original plan:** `docs/superpowers/plans/2026-04-23-api-serving-layer.md`
**Fargate spec:** `docs/superpowers/specs/2026-05-13-fargate-serving-layer-design.md`
**Fargate plan:** `docs/superpowers/plans/2026-05-13-fargate-serving-layer.md`
**Worktree directory:** `.worktrees/` (project-local)

---

## Development Workflow (Superpowers Skills)

Use these skills in sequence for every new feature. Invoke each via the `Skill` tool **before** taking any action in that phase.

| Step | Skill | When to invoke |
|---|---|---|
| 1 | `brainstorming` | Before writing any code — refine idea, explore alternatives, save design doc |
| 2 | `using-git-worktrees` | After design approval — isolated branch, clean test baseline |
| 3 | `writing-plans` | With approved design — bite-sized tasks, exact file paths, complete code |
| 4 | `subagent-driven-development` *(preferred)* or `executing-plans` | With plan — task-by-task with review between each |
| 5 | `test-driven-development` | During implementation — RED → GREEN → REFACTOR; delete pre-test code |
| 6 | `requesting-code-review` | Between tasks — critical issues block progress |
| 7 | `finishing-a-development-branch` | All tasks done — verify tests, merge/PR/discard worktree |

Never skip `brainstorming`. Never write code before a plan exists.

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
mdg/
  src/                       # PHP Symfony source
  tests/                     # PHPUnit tests
  composer.json
  phpunit.xml.dist
  Dockerfile
load_tests/
  newsletter/
    config.js                # Shared k6 constants (BASE_URL, headers, IDs)
    smoke.js                 # 1 VU · sanity check
    newsletter_cached.js     # 500 VUs · p99 < 50ms
    newsletter_uncached.js   # 200 VUs · p99 < 100ms
    mixed_realistic.js       # 1,000 VUs · p95 < 150ms
    deep_dive_sse.js         # 50 VUs · first chunk < 200ms
    capacity_benchmark.js    # 10→200 VUs, observation only
    cold_start_stress.js     # spike 0→1000 VUs · errors<1%
    summary.js               # shared k6 summary helpers
  mdg/                       # (future PHP load tests)
scripts/
  deploy.sh                  # Reads Terraform outputs, deploys SAM stack
  deploy_fargate.sh          # Build Docker image, push to ECR, redeploy ECS
  deploy_k6_runner.sh        # Provision EC2 k6 runner via SSM
migrations/
  001_initial_schema.sql     # All CREATE TABLE + INDEX statements
  002_deep_dives.sql
terraform/
  modules/fargate/           # ECS Fargate, ALB, ECR, security groups, auto-scaling
  envs/dev/                  # dev environment root module
infra/
  template.yaml              # SAM template (Lambda, kept for reference)
config/
  common.yaml / dev.yaml / local.yaml  # Shared YAML config (DB, Redis, AWS)
docker-compose.yml           # Local PostgreSQL + Redis + mdg
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

## Commit Guidelines

Format: `<type>(<scope>): <short description>`

| Type | When |
|---|---|
| `feat` | New endpoint, handler, or behaviour |
| `fix` | Bug fix |
| `test` | Add or fix tests (no production code change) |
| `infra` | SAM template, Docker, migrations |
| `chore` | Dependencies, gitignore, tooling |
| `refactor` | Code change with no behaviour change |
| `docs` | Docs, specs, plans only |

**Rules:**
- Scope = affected module (`newsletters`, `cache`, `db`, `seed`, `infra`, …)
- Max 72 characters on the first line
- Present tense, imperative mood: "add" not "added"
- Each commit leaves tests green

**Examples:**
```
feat(newsletters): add cache-miss fallback to Aurora
test(subscriptions): cover DELETE returns 204 on success
fix(cache): handle Redis unavailable without surfacing error to client
infra(sam): add RDS Proxy endpoint parameter
chore: add psycopg2-binary to requirements.txt
```

---

## Non-Regression Checklist

Before marking any task complete:

```bash
# 1. Full test suite
pytest tests/ -v

# 2. No new test skips introduced
pytest tests/ -v | grep -i skip   # must be empty (or same as before)

# 3. Docker Compose is up for integration smoke (optional, manual)
docker-compose up -d
# run seed.py locally if schema changed
# docker-compose down
```

For load test pass criteria (Phase 1 gate):

| Scenario | Tool | Command | Must pass |
|---|---|---|---|
| Newsletter cached | k6 | `k6 run load_tests/newsletter_cached.js` | p99 < 50ms, 0% errors |
| Newsletter uncached | k6 | `k6 run load_tests/newsletter_uncached.js` | p99 < 100ms, 0% errors |
| Mixed realistic | k6 | `k6 run load_tests/mixed_realistic.js` | 1,000 req/s, p95 < 150ms |
| Deep-dive SSE | k6 | `k6 run load_tests/deep_dive_sse.js` | First chunk < 200ms |
| Capacity benchmark | k6 | `k6 run load_tests/capacity_benchmark.js` | Observation only |

All four gated scenarios must pass before real data integration begins. Capacity benchmark is run for auto-scaling calibration only.

---

## Architectural Decisions

All architectural decisions are recorded in `docs/decisions/`.

**When taking an architectural decision:**

1. Add a row to [`docs/decisions/README.md`](docs/decisions/README.md):
   - `#` → next sequential number
   - `Decision` → what was decided (one phrase)
   - `Chosen` → selected option
   - `Rejected` → alternatives that were not chosen
   - `Justification` → one sentence why

2. Create `docs/decisions/NNN-slug.md` with full ADR:
   - **Context** — what forced the decision
   - **Options Considered** — each option with explicit rejection reasons
   - **Decision** — what was chosen and how it is implemented
   - **Usage** — commands or code showing how to use it
   - **Consequences** — cost, operational impact, future upgrade path

3. Commit both files together: `docs(decisions): ADR-NNN short description`

Never add an ADR detail file without updating `docs/decisions/README.md`, and vice versa.

---

## Out of Scope (Phase 1)

Do not implement, scaffold, or stub:
- NLP / clustering pipeline
- LLM newsletter generation
- Web scraping / source monitoring
- Email delivery
- Frontend / client application
