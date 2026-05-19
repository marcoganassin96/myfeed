# Load Test Targets by Infrastructure Tier

**Discovery date:** 2026-05-13  
**Discovered during:** k6 load test failures — see `docs/troubleshooting/2026-05-09-k6-newsletter-cached-500-errors.md`

---

## Root Discovery: db.t3.micro Connection Limit

`db.t3.micro` has `max_connections ≈ 87–112` (formula: `LEAST({DBInstanceClassMemory/9531392}, 5000)`; 1 GB RAM → ~110).

The Lambda psycopg2 driver opens **one connection per Lambda invocation** — no pool, no reuse across concurrent invocations. With no RDS Proxy:

```
200 concurrent VUs
→ up to 200 concurrent Lambda invocations
→ up to 200 simultaneous Aurora connections
→ db.t3.micro limit: ~110
→ overflow → connection refused → 500 errors
```

This is the structural reason why the `newsletter_uncached` scenario at 200 VUs fails on the free-tier infrastructure. The Fargate asyncpg pool bounds connections at the worker level, and RDS Proxy further multiplexes them — so the same db.t3.micro limit would still apply if the Fargate pool is misconfigured there too.

---

## Connection Budget per Tier

### Free Tier (Lambda + db.t3.micro, no RDS Proxy)

| Component | Value |
|---|---|
| db.t3.micro `max_connections` | ≈ 110 |
| Reserved for RDS internal use | ~10 |
| Available for application | ~100 |
| Lambda model | 1 connection per concurrent invocation |
| Safe concurrent Lambda invocations | ≤ 100 |

### Premium Tier (Fargate + Aurora Serverless v2 + RDS Proxy)

| Component | Value |
|---|---|
| Aurora Serverless v2 `max_connections` | Scales with ACUs; at 2 ACU min ≈ 1,000+ |
| RDS Proxy `max_connections_percent` | 100% (configured in Terraform) |
| asyncpg pool `max_size` per worker | 20 |
| Uvicorn workers per task | 3 |
| ECS tasks (default) | 2 |
| Total backend pool connections | 3 × 20 × 2 = 120 (well within proxy limits) |

RDS Proxy multiplexes: 120 pool slots → proxy → fewer actual Aurora backend connections via connection superposition. Aurora never sees 120 concurrent open connections unless all pool slots are simultaneously active.

**Note on worker count:** 1 worker is correct for free tier — asyncio on an I/O-bound API handles concurrency without multiple processes. Set `UVICORN_WORKERS=3` only when upgrading to premium. See `docs/decisions/003-asyncpg-vs-psycopg3.md`.

---

## Recommended k6 Load Test Targets by Tier

### Free Tier (Lambda + db.t3.micro)

No RDS Proxy. Every uncached request = 1 Aurora connection. Lambda cold starts inside VPC add 2–5s ENI attachment overhead.

| Scenario | Max VUs | Threshold | Reason for cap |
|---|---|---|---|
| `newsletter_cached` | 100 VUs | p99 < 200ms | Redis path; safe below DB connection limit |
| `newsletter_uncached` | **50 VUs** + 30s ramp-up | p99 < 3000ms | DB connection limit caps safe concurrency at ~100; VPC cold start dominates latency |
| `deep_dive_sse` | 20 VUs | first chunk < 2000ms | SSE holds connections open for stream duration |
| `mixed_realistic` | 200 VUs | p95 < 1000ms | Mixed hit rate reduces Aurora pressure; not a hard gate on this tier |
| `cold_start_stress` | 0→100 VUs spike | error rate < 5% | Lambda throttle + DB overflow expected above ~80–100 concurrent |

These are not the original Phase 1 gates. They are the **realistic targets for the free-tier infrastructure**. Use them to validate logic and pipeline correctness, not to gate production readiness.

### Premium Tier (Fargate + Aurora Serverless v2 + RDS Proxy)

RDS Proxy pools backend connections. Fargate has no cold start tax. asyncpg handles async concurrency without 1-connection-per-request overhead.

| Scenario | Max VUs | Threshold | Status |
|---|---|---|---|
| `newsletter_cached` | 500 VUs | p99 < 50ms | Phase 1 gate |
| `newsletter_uncached` | 200 VUs | p99 < 300ms | Phase 1 gate |
| `deep_dive_sse` | 50 VUs | first chunk < 500ms | Phase 1 gate |
| `mixed_realistic` | 1,000 VUs | p95 < 200ms | Phase 1 gate |
| `cold_start_stress` | 0→1,000 VUs spike | error rate < 1% | Phase 1 gate |

These match `docs/superpowers/plans/2026-04-28-restore-premium-infra.md` — the premium infra restore is a prerequisite for hitting these numbers.

---

## Why the Gap Exists

| Factor | Free Tier | Premium Tier |
|---|---|---|
| DB connection limit | ~100 (t3.micro fixed) | ~1,000+ (Aurora Serverless v2 scales with ACUs) |
| Connection pooling | None — Lambda = 1 conn per concurrent invocation | RDS Proxy multiplexes pool → backend connections |
| Cold start overhead | 2–5s VPC ENI attachment per new Lambda container | None — Fargate containers stay warm |
| Connection reuse | Lambda reuses only across sequential warm invocations | asyncpg pool always reuses across async requests |
| Latency floor (DB path) | ~600ms with VPC cold start | < 10ms with warm pool connection |

---

## Related

- [`docs/troubleshooting/2026-05-09-k6-newsletter-cached-500-errors.md`](../troubleshooting/2026-05-09-k6-newsletter-cached-500-errors.md) — original investigation; surfaced connection limit as likely failure cause
- [`docs/decisions/003-asyncpg-vs-psycopg3.md`](../decisions/003-asyncpg-vs-psycopg3.md) — asyncpg pool sizing rationale (3 workers × 20 conn = 60 per task)
- [`docs/decisions/002_lambda-vs-fargate.md`](../decisions/002_lambda-vs-fargate.md) — architectural decision to migrate compute to Fargate
- [`docs/superpowers/plans/2026-04-28-restore-premium-infra.md`](../superpowers/plans/2026-04-28-restore-premium-infra.md) — premium infra restore plan (prerequisite for Phase 1 gate targets)
