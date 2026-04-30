# CLAUDE.md

Guidance for Claude Code when working in this repository.

---

## Project Overview

AWS-native newsletter platform. Currently building the **API / Serving Layer** (Phase 1) with mocked data for load testing. Real NLP/LLM pipeline is out of scope until load tests pass.

**Spec:** `docs/superpowers/specs/2026-04-23-api-serving-layer-design.md`
**Plan:** `docs/superpowers/plans/2026-04-23-api-serving-layer.md`
**Implementation branch:** `feat/api-serving-layer` (branch off `master`)
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
| Runtime | Python 3.12, AWS Lambda |
| API | API Gateway (REST) + Cognito JWT auth |
| Cache | ElastiCache Serverless (Redis), TTL 1h |
| Database | Aurora Serverless v2 (PostgreSQL), via RDS Proxy |
| IaC | AWS SAM (`infra/template.yaml`) |
| Local dev | Docker Compose (PostgreSQL + Redis) |
| Testing | pytest, pytest-mock |
| Load testing | k6 |

---

## File Structure

```
src/
  db.py                    # Aurora connection (psycopg2 + RDS Proxy)
  cache.py                 # Redis client (cache_get / cache_set)
  response.py              # HTTP response builders (ok, not_found, …)
  handlers/
    newsletters.py         # GET /newsletters, GET /newsletters/{id}
    subscriptions.py       # GET/POST/DELETE /subscriptions
    interactions.py        # POST /interactions
    deep_dive.py           # POST /deep-dive/{event_id}  (SSE streaming)
migrations/
  001_initial_schema.sql   # All CREATE TABLE + INDEX statements
scripts/
  seed.py                  # Truncate → insert mock data → pre-warm Redis
  create_test_tokens.py    # Issue 100 Cognito Bearer tokens for load tests
load_tests/
  config.js                # Shared k6 constants
  newsletter_cached.js     # 500 VUs · p99 < 50ms
  newsletter_cold.js       # 200 VUs · p99 < 300ms
  mixed_realistic.js       # 1,000 VUs · p95 < 200ms
  deep_dive_sse.js         # 50 VUs · first chunk < 500ms
  cold_start_stress.js     # Spike 0→1,000 VUs in 10s · errors < 1%
infra/
  template.yaml            # SAM template
docker-compose.yml         # Local PostgreSQL + Redis
tests/
  conftest.py              # mock_db, mock_cache, api_event fixtures
```

---

## Validation — Run After Every Code Change

```bash
# Unit tests (no network required — uses mock_db / mock_cache fixtures)
pytest tests/ -v

# Type check (if mypy is added later)
# mypy src/

# Lint
# ruff check src/ tests/
```

All tests must pass before committing. Zero failures is the bar — no skips allowed unless the test is explicitly marked `@pytest.mark.skip(reason="...")` with a reason.

---

## Coding Standards

### Import pattern — required for testability

Handlers must import modules, not functions, so pytest-mock patches work.
`src/` is the Python root (`pythonpath = src` in pytest.ini; `CodeUri: ../src` in SAM template).

```python
# CORRECT — mocker.patch("db.get_connection") works
import db
import cache

# WRONG — patch has no effect; import already bound the name
from db import get_connection
from cache import cache_get
```

### Handler signature

Every Lambda handler follows this shape:

```python
def handler(event, context):
    # route by resource + httpMethod
    # return response builders from src.response
```

`user_id` is always extracted from `event["requestContext"]["authorizer"]["claims"]["sub"]`. Never accept it as a query/body parameter.

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
# mock_db     → MagicMock cursor; patches src.db.get_connection
# mock_cache  → (mock_get, mock_set); patches src.cache.cache_get / cache_set
# api_event() → factory for API Gateway proxy event dicts

def test_get_newsletter_cache_hit(mock_cache, api_event):
    mock_get, _ = mock_cache
    mock_get.return_value = {"newsletter_id": "abc", "title": "Test"}
    response = handler(api_event("GET", "/newsletters/abc", path_params={"newsletter_id": "abc"}), {})
    assert response["statusCode"] == 200
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
| Newsletter cold | k6 | `k6 run load_tests/newsletter_cold.js` | p99 < 300ms, 0% errors |
| Mixed realistic | k6 | `k6 run load_tests/mixed_realistic.js` | 1,000 req/s, p95 < 200ms |
| Deep-dive SSE | k6 | `k6 run load_tests/deep_dive_sse.js` | First chunk < 500ms |
| Cold start stress | k6 | `k6 run load_tests/cold_start_stress.js` | Error rate < 1% |

All five k6 scenarios must pass before real data integration begins.

---

## Out of Scope (Phase 1)

Do not implement, scaffold, or stub:
- NLP / clustering pipeline
- LLM newsletter generation
- Web scraping / source monitoring
- Email delivery
- Frontend / client application
