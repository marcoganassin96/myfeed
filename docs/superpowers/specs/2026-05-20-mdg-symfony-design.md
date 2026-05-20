# MDG — Master Data Gateway (Symfony) Design

**Date:** 2026-05-20
**Branch:** feat/mdg-symfony
**Related ADRs:** 004 (schema ownership), 005 (service auth), 006 (Redis ownership)

---

## 1. Topology

```
Client
  └─► Public ALB (port 80)
        └─► FastAPI (ECS Fargate) — BFF: JWT auth, response shaping, SSE streaming
              └─► Internal ALB (port 80)
                    └─► MDG (ECS Fargate, Symfony) — data layer, Redis, RDS
                          ├─► ElastiCache Redis   (cache read/write/invalidate, TTL 1h)
                          └─► RDS PostgreSQL       (source of truth, Doctrine ORM)
```

**FastAPI is a pure BFF.** No direct DB or Redis connection for DB-backed data. `db_async.py` and `cache_async.py` stay in repo but are not injected into handlers.

**MDG is private-subnet-only.** No public ALB route. VPC network isolation is the sole security boundary (ADR-005).

---

## 2. MDG API Contract

FastAPI passes `user_id` (extracted from JWT) via `X-User-Id` header on every request. MDG trusts this header — VPC isolation guarantees only FastAPI can reach it. Doctrine global filter uses it to enforce tenant isolation at ORM level (ADR-004).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/master-data/newsletters` | list newsletters |
| `GET` | `/master-data/newsletters/{id}` | single newsletter |
| `GET` | `/master-data/subscriptions` | list subscriptions for user |
| `POST` | `/master-data/subscriptions` | create subscription |
| `DELETE` | `/master-data/subscriptions/{id}` | delete subscription |
| `POST` | `/master-data/interactions` | record interaction |
| `GET` | `/master-data/deep-dive/{event_id}` | fetch persisted result (cache → RDS) |
| `POST` | `/master-data/deep-dive/{event_id}` | store completed deep-dive result |

**Deep-dive flow:**

```
FastAPI receives POST /deep-dive/{event_id}
  └─► GET /master-data/deep-dive/{event_id}
        ├─ HIT  → stream cached result immediately
        └─ MISS → FastAPI processes + streams to client via SSE
                    └─ on completion: POST /master-data/deep-dive/{event_id}
                          └─ MDG persists to RDS + writes Redis
```

Processing and SSE streaming stay in FastAPI. MDG provides persistence and cache for completed results.

---

## 3. MDG Internals (Symfony)

```
mdg/
  src/
    Controller/          — thin HTTP: parse request, call service, return JsonResponse
      NewsletterController.php
      SubscriptionController.php
      InteractionController.php
      DeepDiveController.php
    Service/             — orchestrate: cache check → repository → cache write/invalidate
      NewsletterService.php
      SubscriptionService.php
      InteractionService.php
      DeepDiveService.php
    Repository/          — Doctrine queries only, no cache logic
      NewsletterRepository.php
      SubscriptionRepository.php
      DeepDiveRepository.php
    Entity/              — Doctrine ORM mapped to existing schema (no migrations owned here)
      Newsletter.php
      Subscription.php
      Interaction.php
      DeepDive.php
    EventListener/
      UserContextListener.php  — extracts X-User-Id header, sets on RequestStack
    Cache/
      CacheService.php   — Redis read/write/invalidate wrapper (TTL from config)
  config/
  Dockerfile
  composer.json
```

**Cache key pattern:**

| Data | Key |
|---|---|
| newsletter list (user) | `newsletter:list:{user_id}` |
| single newsletter | `newsletter:{id}` |
| subscription list | `subscription:list:{user_id}` |
| deep-dive result | `deep-dive:{event_id}` |

Write/delete operations invalidate affected keys before returning.

**docker-compose addition:**

```yaml
mdg:
  build: ./mdg
  ports:
    - "9000:9000"
  environment:
    DATABASE_URL: postgresql://newsletter:newsletter@postgres:5432/newsletter
    REDIS_URL: redis://redis:6379
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_started
```

Single `docker-compose up` spins PostgreSQL, Redis, and MDG. FastAPI reaches MDG at `http://mdg:9000` locally.

---

## 4. FastAPI Changes

**New dependency — lifespan-managed shared httpx client:**

```python
# main.py lifespan
@asynccontextmanager
async def lifespan(app):
    app.state.mdg_client = httpx.AsyncClient(
        base_url=settings.mdg.url,
        timeout=httpx.Timeout(
            connect=settings.mdg.connect_timeout,
            read=settings.mdg.read_timeout,
            write=settings.mdg.write_timeout,
            pool=settings.mdg.pool_timeout,
        ),
    )
    yield
    await app.state.mdg_client.aclose()

# dependencies.py
async def get_mdg_client() -> httpx.AsyncClient:
    return app.state.mdg_client
```

**Handler shape after change:**

```python
@router.get("/newsletters/{newsletter_id}")
async def get_newsletter(
    newsletter_id: str,
    mdg: httpx.AsyncClient = Depends(get_mdg_client),
    user_id: str = Depends(get_user_id),
):
    resp = await mdg.get(
        f"/master-data/newsletters/{newsletter_id}",
        headers={"X-User-Id": user_id},
    )
    ...
```

**File-level changes:**

| File | Change |
|---|---|
| `db_async.py` | kept, not injected into handlers |
| `cache_async.py` | kept, not injected into handlers |
| `dependencies.py` | add `get_mdg_client()`, keep `get_user_id()` |
| `handlers/*.py` | drop `get_pool`, `get_redis`; inject `get_mdg_client` |
| `tests/conftest.py` | replace `mock_pool` with `mock_mdg` (`pytest-httpx`) |

**New env var:** `MDG_URL` (resolved from config, not set directly in code).

---

## 5. Error Handling

FastAPI maps MDG responses:

| MDG outcome | FastAPI returns |
|---|---|
| 2xx | pass through |
| 404 | 404 Not Found |
| 400 | 400 Bad Request |
| 5xx | 502 Bad Gateway |
| `ConnectError` / `TimeoutException` | 503 Service Unavailable |

No fallback to direct DB. FastAPI has no pool in handlers. MDG down = 503, full stop. Silent fallback would reintroduce dual cache-ownership problem.

Deep-dive SSE handler uses `settings.mdg.deep_dive_read_timeout` (larger value) since MDG processing takes seconds.

---

## 6. Configuration

**`config/common.yaml`** (new — shared across all environments):

```yaml
mdg:
  connect_timeout: 2.0
  read_timeout: 10.0
  write_timeout: 5.0
  pool_timeout: 2.0
  deep_dive_read_timeout: 60.0

cache:
  ttl: 3600
```

**`config/local.yaml`** (add):

```yaml
mdg:
  url: "http://mdg:9000"
```

**`config/dev.yaml`** (add):

```yaml
mdg:
  url: "http://<internal-alb-dns>"
```

No timeout or TTL literals in code. All values read from `settings.*`.

MDG side (Symfony): reads `DATABASE_URL`, `REDIS_URL`, and timeout/TTL values from `config/packages/mdg.yaml` resolved via `APP_ENV`.

---

## 7. Testing Strategy

**FastAPI — `pytest` + `pytest-httpx`:**

`mock_pool` fixture replaced by `mock_mdg` (intercepts httpx calls). Test cases per handler:
- MDG 200 → correct status + response shape
- MDG 404 → 404
- MDG 5xx → 502
- `ConnectError` → 503
- `TimeoutException` → 503

**MDG — PHPUnit:**

| Layer | Mock | Assert |
|---|---|---|
| Controller | Service | HTTP status, JSON shape |
| Service (read) | CacheService + Repository | HIT → no DB call; MISS → DB called + cache written |
| Service (write) | Repository + CacheService | DB persisted + cache invalidated |
| CacheService | Redis client | key format, TTL set on write |

**Integration tests:** manual only (`docker-compose up`). Not in CI gate — same policy as current setup.

**New dependency:** `pytest-httpx` in `requirements-fargate.txt` (test group).
