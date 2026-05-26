# myfeed

AWS-native newsletter platform that delivers personalised, topic-based daily digests. Events are clustered into narrative threads by an NLP pipeline; an LLM generates the daily narrative and links related past editions for context.

**Phase 1 (current):** API / Serving Layer with mocked data — load-tested to 1,000 req/s before any real pipeline is wired in.

---

## Architecture

```
Client
  │ HTTPS + Bearer <cognito_jwt>
  ▼
ALB (eu-west-1, internet-facing)
  │ HTTP/1.1 → target group port 8000
  ▼
ECS Fargate — newsletter  (FastAPI + uvicorn · 1 vCPU / 2 GB per task · min 0, max 2)
  │  GET /newsletters, GET /newsletters/{id}
  │  GET / POST / DELETE /subscriptions
  │  POST /interactions
  │  POST /deep-dive/{event_id}   [SSE streaming]
  │
  │ internal HTTP  (VPC-only · private subnet · no public route)
  ▼
ECS Fargate — mdg  (PHP 8.4 / Symfony 7 · nginx + PHP-FPM via supervisord · 1 vCPU / 2 GB per task)
  │  GET  /master-data/newsletters/{id}
  │  GET  /master-data/subscriptions
  │  POST /master-data/interactions
  │
  ├── ElastiCache Serverless (Redis)   master data cache · TTL 1h   [owned by MDG]
  └── RDS PostgreSQL db.t3.micro       schema owned by Doctrine ORM
```

Compute infrastructure managed with Terraform (`terraform/`). Legacy SAM template kept in `infra/template.yaml` for reference.

### Why not Lambda

Lambda was the original compute layer and was replaced for two reasons.

**1. Burst throttling makes load-test results meaningless.**
Lambda scales by spinning up one container per concurrent request. Inside a VPC, each new container must attach an ENI before it can reach Redis or Aurora — a 2–5 second overhead. Under a burst of 30 VUs, this produced 2363 throttles in the first 60 seconds before containers warmed up. Steady-state (warm containers) showed zero throttles, meaning the numbers from the load tests depended entirely on whether Lambda happened to be warm — not on the API's real performance. Fargate tasks stay running with ENIs permanently attached, so every request — first or millionth — measures actual handler latency.

**2. Lambda is 10× more expensive at the target scale.**
The didactic scenario is 1 million users generating peaks of 1,000 req/s. At that throughput:

| | Lambda | Fargate (4 tasks) |
|---|---|---|
| Monthly cost | ~$1,922 | ~$185 |
| Cost ratio | 10.4× more expensive | — |

Lambda's per-invocation pricing compounds at scale: each request pays for container spin-up, GB-s of memory, and request fees. Fargate charges for reserved vCPU/memory regardless of request count, so the unit cost collapses as throughput rises. The break-even is ~44 req/s sustained — anything above that, Fargate wins on cost.

Full analysis: [`docs/decisions/002_lambda-vs-fargate.md`](docs/decisions/002_lambda-vs-fargate.md)

---

### Why Redis access moved from newsletter to MDG

Originally FastAPI owned Redis directly: on every request it checked the cache, fell through to Aurora on a miss, and wrote the result back. This worked while FastAPI was the only service writing data.

When MDG was introduced as the authoritative data layer (owning Aurora via Doctrine), a cache invalidation problem appeared: whenever MDG wrote or updated a record, FastAPI's Redis entries became stale. The only way to fix that without moving cache ownership was to have MDG notify FastAPI which keys to drop — but that callback creates a circular dependency (FastAPI → MDG → FastAPI). Every new write path in MDG would have had to remember the invalidation call; a missed call leaves stale data silently.

The fix is to move cache ownership to the writer. MDG now handles all Redis read / write / invalidation internally. FastAPI makes a plain HTTP call to MDG and gets back fresh data — whether that came from Redis or Aurora is MDG's concern, not FastAPI's. Invalidation becomes a local function call inside MDG rather than a distributed coordination protocol across two services.

The performance cost is bounded: a cache hit now travels FastAPI → MDG → Redis instead of FastAPI → Redis, adding ~0.5–2 ms intra-VPC. For the p99 < 50 ms load test target that overhead is negligible.

Full analysis: [`docs/decisions/006-mdg-owns-redis-cache.md`](docs/decisions/006-mdg-owns-redis-cache.md)

---

### Lessons Learned

**RDS/Redis are VPC-private — a bastion is required for local access.**
Both RDS and ElastiCache live in private subnets with no public route. An EC2 bastion in the public subnet bridges local machines into the VPC via SSM port-forwarding. AL2023 AMI ships without SSM agent — install it explicitly via `dnf install amazon-ssm-agent` in Terraform `user_data`. No SSH keys, no open port 22.

**Per-row inserts over a tunnel are catastrophically slow.**
Seed script ran 800 s over the SSM tunnel using per-row `INSERT` loops — each row pays the full round-trip latency. `execute_values` batches all rows into one query: 800 s → 17 s (47× faster). Rule: always bulk-insert over any high-latency connection.

**Lambda cold starts under burst make load-test numbers unreliable.**
Lambda inside a VPC must attach an ENI per new container — 2–5 s overhead. At 1,000 req/s, 2,363 throttles appeared in the first 60 s. A k6 ramp-up warmup stage didn't help because the bottleneck is ENI provisioning, not the handler. Fargate tasks stay permanently warm; every request — first or millionth — measures real handler latency.

**k6 alone can't separate cached from uncached latency.**
Without observability hooks, all requests collapse into a single latency distribution. Two custom response headers solve it: `X-Cache: HIT|MISS` (read as a k6 tag to split metrics by cache source) and `X-Bypass-Cache` (forces a cold Aurora path on demand without flushing Redis). Cache coverage and per-source p99 become directly measurable.

---

### My Progresses

| Area | Technologies | Starting Level | Current Level |
|---|---|---|---|
| Backend framework | PHP, Symfony, Laravel | 2/10 | 4.5/10 |
| Infrastructure | AWS (Fargate, Lambda, EC2, RDS, VPC) | 3/10 | 6/10 |
| Scalability | RDS Proxy, ElastiCache, load testing with k6 | 3/10 | 6/10 |
| Complex Data | DynamoDB, Neo4j/Neptune, pgvector | 3/10 | 3/10 |
| DevOps | Docker, GitHub Actions, CI/CD, Terraform | 6/10 | 6.5/10 |
| Claude Code | Claude Code | 2/10 | 6/10 |

---

## Load Tests

### Last Update: 2024-06-20 - Newsletter Fargate + Redis cache (MDG missing)
k6 was run from an EC2 instance in eu-west-1 (same region as the ALB) in order to measure real network latency and avoid bottlenecks from the local machine's connection. The test ramped up to 100 VUs over 60 seconds.

**Baselines** (k6-newsletter-runner EC2, eu-west-1, 100 VUs):

| Metric | Cached (Redis) | Uncached (Aurora bypass) | Ratio |
|---|---|---|---|
| Throughput | 855 req/s | 569 req/s | 1.5× |
| avg latency | 95 ms | 143 ms | 1.5× |
| p(90) | 109 ms | 257 ms | 2.4× |
| p(95) | 136 ms | 331 ms | 2.4× |
| max | 638 ms | 1,290 ms | 2.0× |

---

## Project Layout

```
src/
  main.py                  FastAPI app, lifespan, router registration
  auth.py                  JWT: JWKS fetch (cached), RS256 verify, 401 on failure
  dependencies.py          get_pool(), get_redis(), get_user_id() — Depends providers
  db_async.py              asyncpg pool factory
  cache_async.py           redis.asyncio client factory
  fields.py                StrEnum constants (unchanged from Lambda)
  response.py              HTTP response builders (unchanged from Lambda)
  db.py                    psycopg2 sync client (Lambda backward compat, kept)
  cache.py                 redis-py sync client (Lambda backward compat, kept)
  handlers/
    newsletters.py         async FastAPI router
    subscriptions.py       async FastAPI router
    interactions.py        async FastAPI router
    deep_dive.py           StreamingResponse + SSE generator
migrations/
  001_initial_schema.sql
scripts/
  seed.py                  Truncate → insert mock data → pre-warm Redis
  create_test_tokens.py    Issue 100 Cognito Bearer tokens for load tests
load_tests/                k6 scenarios
terraform/
  modules/fargate/         ECS Fargate, ALB, ECR, security groups, auto-scaling
  envs/dev/                dev environment root module
infra/
  template.yaml            AWS SAM template (Lambda, kept for reference)
Dockerfile                 python:3.12-slim, uvicorn entrypoint
requirements-fargate.txt   fastapi, uvicorn, asyncpg, redis[asyncio], python-jose
tests/
  conftest.py              pytest fixtures (client, mock_pool — FastAPI TestClient)
docker-compose.yml         Local Postgres + Redis
```

---

## Docs

- [Original API design spec](docs/superpowers/specs/2026-04-23-api-serving-layer-design.md)
- [Original API implementation plan](docs/superpowers/plans/2026-04-23-api-serving-layer.md)
- [Fargate design spec](docs/superpowers/specs/2026-05-13-fargate-serving-layer-design.md)
- [Fargate implementation plan](docs/superpowers/plans/2026-05-13-fargate-serving-layer.md)
- [ADR 002: Lambda vs Fargate](docs/decisions/002_lambda-vs-fargate.md)
- [ADR 003: asyncpg vs psycopg3](docs/decisions/003-asyncpg-vs-psycopg3.md)
