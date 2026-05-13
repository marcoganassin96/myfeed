# Fargate Serving Layer — Design Spec

**Date:** 2026-05-13
**Scope:** Replace Lambda + API Gateway with async FastAPI on ECS Fargate. Keep all existing infrastructure (VPC, Aurora/RDS PostgreSQL, ElastiCache Redis, Cognito). Reuse all k6 load tests with tighter thresholds.

**Supersedes:** `docs/superpowers/specs/2026-04-23-api-serving-layer-design.md` (compute layer only)
**Decision basis:** `docs/decisions/002_lambda-vs-fargate.md`, `docs/decisions/003-asyncpg-vs-psycopg3.md`

---

## 1. Architecture

### Component Diagram

```
Client
  │ HTTPS + Bearer <cognito_jwt>
  ▼
ALB (eu-west-1, internet-facing)
  │ HTTP/1.1 → target group port 8000
  ▼
ECS Fargate Service (desired 0, max 2)
  ├── Task A: FastAPI + uvicorn (1 vCPU, 2 GB)
  └── Task B: FastAPI + uvicorn (1 vCPU, 2 GB)

┌─ VPC (unchanged) ──────────────────────────────────────────┐
│  ElastiCache Serverless (Redis)   RDS PostgreSQL db.t3.micro│
│  redis.asyncio client             asyncpg pool (max 20 conn)│
│                                   direct connect, no proxy  │
└────────────────────────────────────────────────────────────┘

Cognito User Pool (unchanged) — JWKS cached in-process
```

### What Changes vs Lambda

| Component | Lambda (old) | Fargate (new) |
|---|---|---|
| Compute | Lambda per function | Single FastAPI app, all routes |
| Auth validation | API Gateway Cognito Authorizer | FastAPI JWT middleware (python-jose) |
| DB driver | psycopg2 sync | asyncpg async pool |
| Redis client | redis-py sync | redis.asyncio |
| SSE | Lambda Response Streaming (fake body) | FastAPI `StreamingResponse` (real async) |
| IaC | SAM (`infra/template.yaml`) | Terraform `modules/fargate/` |
| Entry point | API Gateway URL | ALB DNS |

### What Stays Unchanged

- VPC, subnets, security groups (extended, not replaced)
- RDS PostgreSQL db.t3.micro endpoint
- ElastiCache Redis endpoint
- Cognito User Pool + all existing test tokens
- All k6 load test scripts (updated thresholds only)
- `src/fields.py` StrEnum constants
- `migrations/`, `scripts/seed.py`, `scripts/create_test_tokens.py`
- `infra/template.yaml` (Lambda infra kept for reference)

### Connection Budget

| Plan | Uvicorn workers | asyncpg max_size | Tasks | Total DB conns |
|---|---|---|---|---|
| Free (db.t3.micro, max ~112) | 1 | 20 | 2 | 40 ✓ |
| Premium (Aurora + RDS Proxy) | 3 | 20 | 2 | 120 ✓ |

`UVICORN_WORKERS` env var — default `1` (free tier), set to `3` on premium upgrade.

### Premium Upgrade Path

When `2026-04-28-restore-premium-infra.md` is applied:
- `DB_HOST` env var changes from `cluster_endpoint` → `rds_proxy_endpoint`
- `UVICORN_WORKERS` changes from `1` → `3`
- asyncpg pool code unchanged — driver connects to proxy endpoint transparently

---

## 2. Application Structure

### File Layout

```
src/
  main.py                  # FastAPI app, lifespan, router registration
  dependencies.py          # get_pool(), get_redis(), get_user_id() — Depends providers
  auth.py                  # JWT: JWKS fetch (cached), RS256 verify, 401 on failure
  db_async.py              # asyncpg pool factory (create_pool wrapper)
  cache_async.py           # redis.asyncio client factory
  handlers/
    newsletters.py         # rewritten as async FastAPI router
    subscriptions.py       # rewritten as async FastAPI router
    interactions.py        # rewritten as async FastAPI router
    deep_dive.py           # rewritten as StreamingResponse + parametric SSE generator
  fields.py                # unchanged — StrEnums reused as-is
  response.py              # unchanged — helpers used for non-streaming routes
  db.py                    # unchanged — kept for Lambda backward compat
  cache.py                 # unchanged — kept for Lambda backward compat
Dockerfile                 # python:3.12-slim, uvicorn entrypoint
requirements-fargate.txt   # fastapi, uvicorn[standard], asyncpg, redis[asyncio], python-jose[cryptography]
```

### App Startup (lifespan)

```python
# main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await create_pool()    # asyncpg
    app.state.redis = await create_redis()  # redis.asyncio
    yield
    await app.state.pool.close()
    await app.state.redis.aclose()

app = FastAPI(lifespan=lifespan)
```

### Dependency Injection

```python
# dependencies.py
async def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool

async def get_redis(request: Request):
    return request.app.state.redis

async def get_user_id(token: str = Depends(oauth2_scheme)) -> str:
    return auth.verify(token)   # raises HTTP 401 on invalid/expired
```

### Route Shape

```python
# handlers/newsletters.py
@router.get("/newsletters/{newsletter_id}")
async def get_newsletter(
    newsletter_id: str,
    pool: asyncpg.Pool = Depends(get_pool),
    redis = Depends(get_redis),
    user_id: str = Depends(get_user_id),
):
    key = f"{CachePrefix.NEWSLETTER}{newsletter_id}"
    hit = await redis.get(key)
    if hit:
        return JSONResponse(json.loads(hit), headers={HttpHeader.X_CACHE: CacheStatus.HIT})
    row = await pool.fetchrow(_GET_SQL, newsletter_id)
    if row is None:
        return not_found("Newsletter not found")
    ...
```

asyncpg placeholder syntax: `$1, $2, …` (replaces psycopg2 `%s`).
asyncpg returns `asyncpg.Record` — convert to `dict` via `dict(row)` where needed.

### SSE Deep-Dive (parametric)

```python
# handlers/deep_dive.py

_DEFAULT_CHUNKS = [
    "This event marks a significant development in the ongoing story.",
    " Historical context: previous events in this thread laid the groundwork.",
    " Industry analysts expect broad adoption within the next quarter.",
    " Related threads suggest this will accelerate parallel developments.",
]

def get_deep_dive_chunks() -> list[str]:
    return _DEFAULT_CHUNKS   # override in tests via dependency_overrides

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
    return StreamingResponse(_sse_stream(chunks, interval), media_type=ContentType.SSE)
```

`EnvVar.DEEP_DIVE_INTERVAL` added to `src/fields.py`.

### Pydantic Request Bodies

FastAPI validates request bodies automatically. Manual `bad_request` field checks replaced:

```python
class InteractionRequest(BaseModel):
    event_id: str
    type: InteractionType   # StrEnum — membership validated automatically → 422 on invalid
```

### Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements-fargate.txt .
RUN pip install --no-cache-dir -r requirements-fargate.txt
COPY src/ ./src/
WORKDIR /app/src
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

`UVICORN_WORKERS` is not baked into the image — Terraform task definition injects it per environment.

---

## 3. Infrastructure (Terraform)

### New Module: `terraform/modules/fargate/`

| Resource | Purpose |
|---|---|
| `aws_ecr_repository` | Store Docker image |
| `aws_ecs_cluster` | Fargate cluster |
| `aws_ecs_task_definition` | 1 vCPU / 2 GB, env vars + secrets injected |
| `aws_ecs_service` | desired_count = 0, launch_type = FARGATE |
| `aws_appautoscaling_target` | min 0, max 2 tasks |
| `aws_appautoscaling_policy` | CPU target tracking at 70% |
| `aws_lb` | internet-facing ALB |
| `aws_lb_target_group` | port 8000, health check `GET /health` |
| `aws_lb_listener` | port 80 → target group |
| `aws_security_group.alb` | ingress 80 from `0.0.0.0/0`; egress 8000 to `fargate_sg` |
| `aws_security_group.fargate` | ingress 8000 from `alb_sg`; egress 5432/6379/443 |
| `aws_security_group_rule.fargate_to_aurora` | adds ingress 5432 from `fargate_sg` to existing `aurora_sg` |
| `aws_security_group_rule.fargate_to_redis` | adds ingress 6379 from `fargate_sg` to existing `redis_sg` |
| `aws_iam_role` + policy | ECS task execution role — ECR pull + CloudWatch logs |

Module inputs: `aurora_sg_id`, `redis_sg_id` (from `module.vpc` outputs, already exported).
Lambda SG ingress rules on aurora/redis SGs remain — Lambda infra untouched.

### Security Group Design (both plans)

```
Free plan:
  [internet] →80→ [alb_sg] →8000→ [fargate_sg] →5432→ [aurora_sg] → db.t3.micro
                                                 →6379→ [redis_sg] → ElastiCache
                                                 →443→  0.0.0.0/0   (Cognito JWKS)

Premium plan (after restore):
  [internet] →80→ [alb_sg] →8000→ [fargate_sg] →5432→ [aurora_sg] → RDS Proxy → Aurora v2
                                                 →6379→ [redis_sg] → ElastiCache
                                                 →443→  0.0.0.0/0   (Cognito JWKS)
```

`aurora_sg` is the same SG in both plans — proxy reuses it. Fargate module targets same SG ID.

### Auto-Scaling Strategy

**Primary: CPU target tracking (self-calibrating)**
```hcl
resource "aws_appautoscaling_policy" "cpu" {
  policy_type = "TargetTrackingScaling"
  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 70.0
  }
}
```

**Optional post-benchmark: ALBRequestCountPerTarget**
```hcl
# TODO: set after running load_tests/capacity_benchmark.js
# threshold = safe_req_s × 60 × 0.7  (req/min per target, 30% safety margin)
# variable "alb_req_count_threshold" { default = null }
```

Scale-to-zero: `desired_count = 0` at rest. Before load tests, scale to 2 via pipeline.

### Env Vars Injected by Task Definition

```hcl
environment = [
  { name = "DB_HOST",              value = module.aurora.cluster_endpoint },
  { name = "DB_NAME",              value = var.db_name },
  { name = "DB_USER",              value = var.db_user },
  { name = "REDIS_HOST",           value = module.redis.redis_endpoint },
  { name = "REDIS_SSL",            value = "true" },
  { name = "COGNITO_USER_POOL_ID", value = var.cognito_user_pool_id },  # SAM-managed; passed as Terraform var
  { name = "AWS_REGION",           value = var.region },
  { name = "DEEP_DIVE_INTERVAL",   value = "0.05" },
  { name = "UVICORN_WORKERS",      value = "1" },
]
secrets = [
  { name = "DB_PASSWORD", valueFrom = module.aurora.secret_arn },
]
```

### New Terraform Outputs

```hcl
output "alb_dns"      # replaces ApiUrl — used in k6 config.js BASE_URL
output "ecr_repo_url" # used in scripts/deploy_fargate.sh for docker push
```

---

## 4. Testing

### Fixture Pattern (replaces mock_db / mock_cache)

```python
# tests/conftest.py
from fastapi.testclient import TestClient
from main import app
from dependencies import get_pool, get_redis, get_user_id

@pytest.fixture
def mock_pool():
    conn = AsyncMock()
    pool = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn

@pytest.fixture
def client(mock_pool):
    pool, _ = mock_pool
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_redis] = lambda: AsyncMock()
    app.dependency_overrides[get_user_id] = lambda: "test-user-sub"
    yield TestClient(app)
    app.dependency_overrides.clear()
```

### asyncpg Mock Return Values

`fetchrow` / `fetch` return `dict`, not cursor rows:

```python
mock_conn.fetchrow.return_value = {"newsletter_id": "abc", "title": "Test", ...}
mock_conn.fetch.return_value = [{"newsletter_id": "abc", ...}]
mock_conn.fetchrow.return_value = None   # triggers 404
```

### Coverage Bar Per Handler

- Redis hit → pool not acquired
- Redis miss → `fetchrow`/`fetch` called, result cached
- DB returns `None` / `[]` → 404
- Invalid body → 422 (Pydantic, automatic)
- Missing/expired JWT → 401
- SSE deep-dive → chunks received in order, `done: true` as final event
- SSE parametric → `get_deep_dive_chunks` and `get_chunk_interval` overridden via `dependency_overrides`

### SSE Test Override

```python
def client_with_sse_overrides(chunks, interval=0):
    from handlers.deep_dive import get_deep_dive_chunks, get_chunk_interval
    app.dependency_overrides[get_deep_dive_chunks] = lambda: chunks
    app.dependency_overrides[get_chunk_interval] = lambda: interval
    ...
```

---

## 5. Pipeline Integration

### New Steps in `scripts/steps.py`

```python
class Step(StrEnum):
    # existing (Lambda) — unchanged
    SEED = "seed"; TOKENS = "tokens"; IDS = "ids"
    SMOKE = "smoke"; FLUSH = "flush"; UNCACHED = "uncached"
    PREWARM = "prewarm"; CACHED = "cached"; SSE = "sse"
    MIXED = "mixed"; STRESS = "stress"
    # new (Fargate)
    DEPLOY     = "deploy"     # docker build + ECR push + ecs update-service --force-new-deployment
    SCALE_UP   = "scale_up"   # desired_count=2 + poll until 2 tasks RUNNING (~60s)
    BENCHMARK  = "benchmark"  # capacity_benchmark.js — observation only, no pass/fail
    SCALE_DOWN = "scale_down" # desired_count=0

FARGATE_STEP_ORDER: list[Step] = [
    Step.DEPLOY, Step.SCALE_UP,
    Step.SEED, Step.TOKENS, Step.IDS,
    Step.SMOKE, Step.FLUSH, Step.UNCACHED, Step.PREWARM,
    Step.CACHED, Step.SSE, Step.MIXED, Step.BENCHMARK,
    Step.SCALE_DOWN,
]
```

### Pipeline CLI

```bash
# Full Fargate pipeline
CONFIG=config/dev.yaml DB_PASSWORD=<secret> python scripts/pipeline.py --runtime fargate

# Resume from a step (skip deploy/scale_up if tasks already running)
python scripts/pipeline.py --runtime fargate --from-step smoke

# Lambda pipeline unchanged
python scripts/pipeline.py --runtime lambda
```

`SCALE_DOWN` always runs — pipeline wraps load test steps in `try/finally`:

```python
if runtime == "fargate" and Step.SCALE_UP in steps:
    try:
        run_pipeline(steps_without_scale_down, ...)
    finally:
        runners[Step.SCALE_DOWN]()
```

### Capacity Benchmark Script

New file: `load_tests/capacity_benchmark.js`

Stages: 10 → 25 → 50 → 100 → 150 → 200 VUs, 2 min each. No thresholds — observation only.

**After running benchmark:**

1. Find last stage where p99 < 100ms AND error_rate < 0.1% → call that req/s value `S`
2. Note CPU% at that stage → set as `target_value` in Terraform `aws_appautoscaling_policy`
3. Optional ALBRequestCountPerTarget threshold = `S × 60 × 0.7` req/min per target
4. Update Terraform, re-apply

---

## 6. Load Test Thresholds (Updated)

| Scenario | Lambda | Fargate | Reason tighter |
|---|---|---|---|
| Newsletter cached | p99 < 50ms | p99 < 50ms | same |
| Newsletter uncached | p99 < 300ms | p99 < 100ms | no VPC ENI cold start |
| Mixed realistic | p95 < 200ms | p95 < 150ms | persistent connections |
| Deep-dive SSE first chunk | < 500ms | < 200ms | no cold start |
| Cold start stress | errors < 1% | replaced by `benchmark` | not applicable — tasks pre-warmed |

k6 `config.js` change: `BASE_URL` points to ALB DNS instead of API Gateway URL.
All other test logic unchanged.

---

## 7. Error Handling

| Error | Handling |
|---|---|
| Cognito token expired/invalid | FastAPI JWT middleware → 401 |
| asyncpg connection timeout | `command_timeout=5` on pool → DB error → 503 |
| Redis unavailable | Falls through to Aurora; no error surfaced to client |
| Aurora unreachable | Pool exhausted → 503 after timeout |
| SSE stream interrupted | Client receives partial events; `done: true` never arrives |
| ECS task unhealthy | ALB routes to remaining task; auto-scaling adds replacement |
| Scale-up timeout | `wait_for_tasks_running.sh` fails → pipeline exits → SCALE_DOWN runs via finally |

---

## 8. Out of Scope (this phase)

Same as Phase 1:
- NLP/clustering pipeline
- LLM newsletter generation
- Real web scraping / source monitoring
- Email delivery
- Frontend / client application
- HTTPS on ALB (dev uses HTTP; add ACM cert + listener rule for prod)
- Multi-region / blue-green deployment
