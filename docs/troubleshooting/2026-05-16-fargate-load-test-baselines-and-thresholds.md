# Fargate Load Test — Baselines, Bottleneck Investigation, and Threshold Methodology

**Date:** 2026-05-16
**Environment:** `newsletter-dev` — Fargate serving layer (`feat/fargate-serving-layer`)
**Status:** Active investigation — only `newsletter_uncached` scenario run so far

---

## 1. Current Infrastructure State

| Component | Config |
|---|---|
| ECS tasks | 2 (set by `scale_up` step in `pipeline.py`) |
| Uvicorn workers per task | 1 (`UVICORN_WORKERS=1`, free-tier default) |
| Total async workers | 2 |
| DB connection | Direct to Aurora Serverless v1 cluster endpoint (no RDS Proxy) |
| asyncpg pool per worker | `min_size=2`, `max_size=10` (check `src/db.py`) |
| Redis | ElastiCache Serverless, SSL enabled, private subnet |
| Load balancer | ALB, HTTP:80, public subnets |
| k6 runner location | Local machine (Windows, EU) — **not co-located with ALB** |

> **No RDS Proxy in current deployment.** The `load-test-targets-by-tier.md` "Premium Tier" table lists RDS Proxy as a future prerequisite — it is not yet wired into the Fargate Terraform module.

---

## 2. Measured Metrics — `newsletter_uncached` (2026-05-16)

**Scenario config:** 200 VUs, 30s warmup (30 VUs → `/health`) + 65s load phase, no sleep.

### Cache breakdown

| Source | Requests | OK% | avg | p(90) | p(95) |
|---|---|---|---|---|---|
| Redis HIT | 49,176 | 100% | 252ms | 233ms | 489ms |
| Aurora MISS | 141 | 100% | 563ms | 1,110ms | 1,260ms |
| **All load** | **49,317** | **100%** | **215ms** | **231ms** | **272ms** |

**Throughput:** ~492 req/s (load phase), ~601 req/s total  
**Error rate:** 0.00%  
**Cache hit ratio:** 99.7% Redis HIT — virtually no Aurora misses

### Key observation

The scenario is named "uncached" but 99.7% of requests hit Redis. The seed script pre-warms all newsletter IDs into Redis. To actually exercise the Aurora path, Redis must be flushed or IDs outside the seed set must be requested. See §5 for implications on scenario design.

---

## 3. Why These Metrics? Bottleneck Investigation Guide

The measured latencies (252ms Redis HIT avg, 563ms Aurora MISS avg) are higher than expected for a warm in-region service. Possible causes, ranked by likelihood:

### 3.1 k6 runner is not co-located (highest impact on absolute numbers)

k6 runs on a local EU Windows machine. Every request traverses:
```
Local machine → ISP → internet → eu-west-1 ALB → Fargate → Redis/Aurora
```

Round-trip from EU to `eu-west-1` is typically **20–50ms base latency** (ping). However, full HTTP round-trip overhead (TCP connection, TLS, ALB processing) is much higher — see §7 "Runner comparison" for measured delta.

**How to isolate:** Run k6 from an EC2 instance in `eu-west-1` (same VPC or same region). Compare results. If Redis HIT drops from 252ms to ~20ms, the bottleneck is network, not the service.

```bash
# From an EC2 instance in eu-west-1
k6 run --env BASE_URL=http://<alb-dns> load_tests/newsletter_uncached.js
```

**Resolution (2026-05-18):** EC2 runner deployed in `eu-west-1` (same VPC as ALB, instance `i-098ca46dbc8ddc3c0`). Hypothesis confirmed — see §7 runner comparison. Redis HIT avg dropped from 233ms → 102ms. Network was dominant factor in EU measurements.

### 3.2 Redis SSL handshake per connection

`REDIS_SSL=true`. SSL adds ~5–20ms per new connection. asyncio reuses connections within a session, but each new Fargate task / worker startup pays this cost.

**How to check:** Look at CloudWatch metrics for `ElastiCache/CacheConnections` during the test. High new connection rate = SSL overhead accumulating.

### 3.3 Single uvicorn worker per task (event loop saturation)

`UVICORN_WORKERS=1` means 2 total workers across 2 tasks. Each worker handles concurrency via asyncio, but at 200 VUs with ~252ms avg latency, each worker handles ~(200 VUs / 2 workers) = 100 concurrent requests. asyncio can handle this, but the event loop may saturate if any handler is not fully async.

**How to check:**
```bash
# Watch ECS CPU metrics during test
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ClusterName,Value=newsletter-dev-cluster \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 --statistics Average --region eu-west-1
```

If CPU is near 100% during test → worker saturation → consider `UVICORN_WORKERS=2` or adding a 3rd task.

### 3.4 Aurora cold connections (no RDS Proxy)

With no RDS Proxy, Aurora sees direct connections from asyncpg pool. On test start, pool connections are cold. Aurora Serverless v1 may also scale ACUs mid-test if the first burst is larger than the current allocated capacity.

**How to check:**
```bash
# Check Aurora connection count during test
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBClusterIdentifier,Value=newsletter-dev-cluster \
  --start-time <test-start> --end-time <test-end> \
  --period 10 --statistics Maximum --region eu-west-1
```

Aurora MISS p(90)=1,110ms at only 141 requests is high — suggests Aurora ACU scaling or cold pool connections dominate, not query time.

### 3.5 ALB → Fargate cross-AZ routing

ALB may route to a Fargate task in a different AZ than the Redis endpoint, adding ~1ms per cross-AZ hop (minor).

---

## 4. How to Choose Thresholds (SLA Enforcement Approach)

Since the goal is **SLA enforcement** (not just regression detection), thresholds must represent real commitments to API consumers. Steps:

### Step 1: Collect full baselines

Run all 5 scenarios and record p(50), p(90), p(95), p(99) per cache tier:

```bash
k6 run load_tests/newsletter_cached.js    # Redis-only baseline
k6 run load_tests/newsletter_uncached.js  # already done — 2026-05-16
k6 run load_tests/mixed_realistic.js      # Aurora read+write paths
k6 run load_tests/deep_dive_sse.js        # SSE stream duration
k6 run load_tests/cold_start_stress.js    # error rate under spike
```

Record results in §6 (Baseline Registry) when run.

### Step 2: Separate thresholds by cache tier

A single blended `http_req_duration` threshold mixes Redis (252ms) and Aurora (563ms) paths, making it impossible to tune without measuring the right thing. Use:

```js
// In newsletter scenarios:
thresholds: {
  "req_by_cache{cache:HIT}":  ["p(99)<Xms"],   // Redis path SLA
  "req_by_cache{cache:MISS}": ["p(99)<Yms"],   // Aurora path SLA
  "http_req_failed":          ["rate<0.001"],
}
```

### Step 3: Set SLA from k6 runner perspective

SLA must be set for the same measurement point as the load test runner. Two valid choices:

| Choice | Runner location | Threshold includes | When to use |
|---|---|---|---|
| **Client-side SLA** | Local EU machine | Round-trip + server | When API consumers are external (EU users) |
| **Server-side SLA** | EC2 in eu-west-1 | Server processing only | When testing service internals, not user experience |

**Recommendation:** Run baseline from EC2 in `eu-west-1` to get server-side numbers first. Then add ~50ms for client-side SLA. Avoids setting thresholds that include your local ISP's latency.

### Step 4: Apply headroom

SLA threshold = measured p(99) × 1.3 (30% headroom for variance).  
Do not set thresholds tighter than measured baseline — that guarantees failure.

Example from current data (local runner, not server-side):

| Path | Measured p(99)* | Proposed SLA threshold |
|---|---|---|
| Redis HIT | ~520ms | 700ms |
| Aurora MISS | ~1,400ms | 1,800ms |

*p(99) estimated from uncached run. Run newsletter_cached for Redis-only p(99) under 500 VUs.

---

## 5. Scenario Design — Cached vs Uncached Split

### Current problem

Both `newsletter_cached` and `newsletter_uncached` exercise the Redis path almost exclusively. Seed pre-warms all newsletter IDs, so there are no cache misses unless Redis is flushed between runs or requests use IDs outside the seed set.

| Scenario | Intended path | Actual path (2026-05-16) |
|---|---|---|
| `newsletter_cached` | 100% Redis HIT | 100% Redis HIT (probably) |
| `newsletter_uncached` | Mix of HIT + MISS | 99.7% Redis HIT, 0.3% MISS |

### Implications

1. **Scenario names are misleading.** `newsletter_uncached` does not test Aurora at realistic scale.
2. **Aurora MISS SLA cannot be validated** until a scenario forces cache misses.
3. **Splitting by tier is correct**, but the underlying scenario design must actually produce MISSes.

### Options to produce Aurora MISSes

| Option | Effort | Notes |
|---|---|---|
| Flush Redis before uncached scenario | Low | `redis-cli FLUSHALL` via bastion; re-warms during test naturally |
| Use IDs outside seed set | Medium | Requires ID range split in `config.js` |
| TTL-based expiry | High | Set Redis TTL to 30s; natural churn during 60s test |

**Recommendation:** Flush Redis before running "uncached" scenario. Add a `redis_flush` step to the pipeline between seed and the uncached run, or document it as a manual prerequisite.

---

## 6. How to Validate Thresholds Are Acceptable

A threshold is acceptable when **all three conditions are met**:

1. **Baseline coverage:** Threshold set after at least 3 independent runs, not a single measurement. Single runs can be affected by Aurora ACU scaling, NAT gateway congestion, or local ISP variance.

2. **k6 runner consistency:** All baseline runs use the same runner location (local or EC2). Mixing locations makes baselines incomparable.

3. **Product agreement:** SLA threshold written in the plan/spec and acknowledged. If no stakeholder has agreed to "Redis HIT p(99) < 700ms", the threshold is still arbitrary — just data-informed arbitrary.

### Anti-patterns to avoid

| Anti-pattern | Why wrong |
|---|---|
| `p(99)<50ms` on Fargate | Below minimum round-trip from EU to eu-west-1 |
| Single threshold mixing HIT + MISS | Passes if 99% are HITs, even if MISS is 5s |
| Threshold set during first run | Single-sample noise; Aurora cold start inflates p(99) |
| Same threshold for cached and uncached scenarios | Different infrastructure paths have different latency floors |

---

## 7. Baseline Registry

> **Two-run rule:** First run includes Aurora cold-start + Fargate task startup overhead. Always compare run 1 vs run 2 to distinguish cold vs warm steady-state. Use run 2+ for threshold calibration.

### `newsletter_uncached` — 200 VUs, local EU runner

| Run | Date | HIT avg / p(90) / p(95) / max | MISS avg / p(90) / p(95) | Throughput | Errors | Notes |
|---|---|---|---|---|---|---|
| 1 | 2026-05-16 | 252ms / 233ms / 489ms / 5.6s | 563ms / 1,110ms / 1,260ms | 492 req/s | 0% | Cold Aurora + cold Fargate connections |
| 2 | 2026-05-16 | 233ms / 228ms / **232ms** / 2.2s | 142ms / 294ms / 339ms | 535 req/s | 0% | Warm steady-state — best result |
| 3 | 2026-05-16 | 285ms / 775ms / **840ms** / 10.9s | — (0 MISSes) | 436 req/s | 0% | Regression: p(95) 3.6× run 2 |

**Cross-run variance is too high to set SLA thresholds.** p(95) swings from 232ms to 840ms across back-to-back runs with identical config. Throughput also varies (535→436 req/s). Root cause must be identified before thresholds are meaningful.

**Run 2 observation:** Aurora MISS (142ms avg) is **faster** than Redis HIT (233ms avg). Redis overhead (SSL + network hop to ElastiCache) exceeds asyncpg pool query time once pool is warm.

### Variance investigation — run 3 regression

Three candidate causes:

| Cause | Signal | How to check |
|---|---|---|
| **ElastiCache Serverless ECU throttle** | ECU limit depleted after back-to-back runs with no cooldown | CloudWatch `ElastiCache/EngineCPUUtilization` and `Throttled` during run 3 |
| **aioredis pool SSL burst** | `max_connections=None` → pool grows to ~100 connections/task under 200 VUs; each new connection pays SSL handshake | CloudWatch `ElastiCache/CurrConnections` spike at test start |
| **Local ISP path variance** | Internet routing to eu-west-1 varies run-to-run | Compare `http_req_blocked` across runs; if blocked avg is high in run 3, it's network |

Run 3 `http_req_blocked` avg=464µs (vs run 2: 383µs) — marginal, so pure ISP variance is not the primary cause.

**Recommended next check:**
```bash
# Check ElastiCache metrics for run 3 window (adjust --start-time / --end-time)
aws cloudwatch get-metric-statistics \
  --namespace AWS/ElastiCache \
  --metric-name CurrConnections \
  --start-time 2026-05-16T14:00:00Z \
  --end-time 2026-05-16T15:00:00Z \
  --period 60 --statistics Maximum \
  --region eu-west-1

# Also check ECS CPU (worker saturation)
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ClusterName,Value=newsletter-dev-cluster \
  --start-time 2026-05-16T14:00:00Z \
  --end-time 2026-05-16T15:00:00Z \
  --period 60 --statistics Maximum \
  --region eu-west-1
```

**Possible fix — explicit Redis pool sizing:**

`cache_async.py` creates `aioredis.Redis()` with no pool cap (`max_connections=None`). Under 200 VUs hitting 2 tasks (100 concurrent/task), the pool creates ~100 connections per task, all paying SSL handshake on first burst. Capping the pool and pre-warming it limits connection churn:

```python
# cache_async.py — explicit pool cap
return aioredis.Redis(
    host=..., port=..., ssl=ssl, decode_responses=True,
    max_connections=20,   # match expected concurrent Redis ops per worker
)
```

Do not change until CloudWatch confirms connection spike is the cause.

### `newsletter_uncached` — 200 VUs, EC2 eu-west-1 runner (2026-05-18)

EC2 instance `i-098ca46dbc8ddc3c0`, eu-west-1a public subnet, same VPC as ALB. Provisioned via `scripts/deploy_k6_runner.sh`. Fargate task count: 2, UVICORN_WORKERS=1.

| Run | Date | HIT avg / p(90) / p(95) / max | MISS avg / p(90) / p(95) | Throughput (cache_count) | Errors | Notes |
|---|---|---|---|---|---|---|
| 1 | 2026-05-18 | 102ms / 181ms / 202ms / 4.01s | 71ms / 264ms / 313ms | 1,221 req/s | 0% | Threshold `p(99)<100ms` crossed; small MISS sample (112 reqs) |

**Threshold failure:** `http_req_duration{scenario:load}` — p(95)=201.58ms; p(99) estimated ~300ms+. Threshold `p(99)<100ms` is unrealistic for the current stack (ElastiCache SSL + ALB overhead alone exceeds 100ms at 200 VUs). Must be recalibrated — see §4.

**Aurora MISS caveat:** 112 MISS requests is a small sample. p(90) and p(95) inflated by Aurora cold pool connections on test start. Flush Redis and re-run for stable MISS baseline.

---

### Runner comparison — EU local vs EC2 eu-west-1

Comparison uses run 2 (best local result) vs EC2 run 1. Load levels differ: EC2 handled 2.3× higher throughput, so server-side latency was under more pressure — the EU overhead is likely understated in raw deltas.

| Metric | Local EU (run 2, 2026-05-16) | EC2 eu-west-1 (run 1, 2026-05-18) | Delta (EU overhead) |
|---|---|---|---|
| Redis HIT avg | 233ms | 102ms | **−131ms** |
| Redis HIT p(90) | 228ms | 181ms | −47ms |
| Redis HIT p(95) | 232ms | 202ms | −30ms |
| Aurora MISS avg | 142ms | 71ms | −71ms |
| Throughput (cache_count) | 535 req/s | 1,221 req/s | +2.3× |

**Aurora MISS faster than Redis HIT (EC2 run) — investigate:** Aurora MISS avg (71ms) < Redis HIT avg (102ms). Counter-intuitive — Aurora requires an asyncpg pool query while Redis is an in-memory cache. Likely explanation: the 112 MISS requests occurred early before Fargate workers reached full concurrency pressure. At low VU count, event loop queuing and ElastiCache connection pool churn are minimal, so the raw query path (asyncpg → Aurora) was faster than a congested Redis SSL connection pool at 200 VUs. **Must investigate:** correlate MISS request timestamps within the k6 run against VU ramp-up curve. If MISSes are front-loaded (first 10s of load phase), the comparison is not apples-to-apples. A Redis flush + re-run will produce MISSes distributed across all 200 VUs and should show MISS >> HIT as expected.

**Round-trip overhead estimate:** The avg delta of **~131ms** is the measured HTTP round-trip cost of the EU → eu-west-1 internet path, including TCP connection, TLS negotiation, and ALB ingress. This is significantly higher than the "20–50ms" ping estimate in §3.1 because k6 measures full HTTP RTT, not ICMP. At p(95) the delta compresses to ~30ms because the EC2 run was under 2.3× higher concurrency, pushing server-side p(95) up and narrowing the gap.

**Adjusted round-trip estimate:** Accounting for EC2 higher load, true EU HTTP overhead is estimated at **130–150ms** (avg path) and **50–100ms** (p(95) path, as server-side variance dominates at tail).

**Key finding from §3.1 hypothesis:** Network was the dominant factor. Redis HIT avg dropped 131ms (−56%) by moving the runner into the same region. The service itself processes warm Redis hits in ~100ms from EC2, which is still higher than expected (see §3.2 — ElastiCache SSL handshake, and §3.3 — event loop saturation at 200 VUs/2 workers).

**Threshold implications:** Thresholds must be set from a consistent runner location. EC2 in eu-west-1 is the correct baseline for server-side SLA. `p(99)<100ms` was set without baseline data and is not achievable with the current ElastiCache SSL configuration at 200 VUs. Recommended recalibration — see §4.

---

### Remaining scenarios (not yet run)

| Scenario | VUs | Redis HIT p(99) | Aurora MISS p(99) | Throughput | Errors |
|---|---|---|---|---|---|
| `newsletter_cached` | 500 | — | — | — | — |
| `mixed_realistic` | 1000 | — | — | — | — |
| `deep_dive_sse` | 50 | — | — | — | — |
| `cold_start_stress` | 0→1000 | — | — | — | — |

---

## Related

- [`docs/how-to/load-test-targets-by-tier.md`](../how-to/load-test-targets-by-tier.md) — connection budget + tier comparison
- [`docs/decisions/002_lambda-vs-fargate.md`](../decisions/002_lambda-vs-fargate.md) — why Fargate was chosen
- [`docs/decisions/003-asyncpg-vs-psycopg3.md`](../decisions/003-asyncpg-vs-psycopg3.md) — asyncpg pool sizing rationale
- [`load_tests/newsletter_uncached.js`](../../load_tests/newsletter_uncached.js) — scenario with uncached threshold
- [`scripts/deploy_fargate.sh`](../../scripts/deploy_fargate.sh) — redeploy script
