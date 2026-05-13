# Lambda vs Fargate: Scaling Decision

**Context:** Newsletter API serving layer. AWS Lambda (Python 3.12, VPC, ElastiCache + Aurora).  
**Problem observed:** 2363 Lambda throttles in 60 seconds under 30-VU load test burst.

---

## Why Lambda Throttled

### One container per concurrent request

Lambda scales horizontally. A single container handles one request at a time. 200 simultaneous requests require 200 containers.

```
Lambda model:
  Request A ──► Container 1  (handles A, then idle)
  Request B ──► Container 2  (handles B, then idle)
  Request C ──► Container 1  (reused — A is done)
  Request D ──► Container 3  (C still on Container 1)

Fargate model (async FastAPI):
  Request A ──┐
  Request B ──┤ Container 1  (event loop handles all concurrently)
  Request C ──┤
  Request D ──┘
```

### VPC cold start overhead

Lambda inside VPC must attach an ENI (Elastic Network Interface) to reach ElastiCache and Aurora. ENI attachment adds **2–5 seconds** to every new container start. This overhead does not exist in Fargate — the ENI attaches once when the task starts and stays attached.

```
Lambda cold start path:
  Request → spin up container → attach ENI → init Python + psycopg2 → handle
              └── 2–5 seconds ──────────────────────────────────────────────┘

Lambda warm path:
  Request → container already running → handle
              └── <100ms ───────────────┘

Fargate (any request after task is running):
  Request → container already running, ENI attached → handle
              └── <100ms ────────────────────────────┘
```

### What happened during the load test

The warmup scenario (30 VUs hitting `/health`) triggered 30 simultaneous cold starts. With 2–5s per cold start, containers were still initialising while new requests arrived. Lambda's burst provisioning could not keep pace → throttle.

CloudWatch evidence:

| Window | Throttles | Phase |
|---|---|---|
| t=0–60s | **2363** | Warmup burst onset |
| t=60–120s | **735** | Warmup tailing off, load starting |
| t=120–180s | **0** | Load phase steady-state |

Zero throttles once containers were warm confirms the problem is **burst provisioning speed**, not steady-state capacity.

---

## Lambda vs Fargate: Concurrency Model Comparison

| Property | Lambda | Fargate (async FastAPI) |
|---|---|---|
| Requests per container | 1 | Hundreds–thousands (I/O-bound) |
| Cold start | 2–5s (VPC) | 30–60s (task launch, once) |
| ENI attachment | Per new container | Once per task, persistent |
| Scaling unit | Container per concurrent request | Task per ~300–500 req/s |
| Burst from zero | Instant (within burst limit) | 60–90s to add task |
| DB connections | New pool per container | Persistent pool, reused |
| Ops complexity | None | ECS, ALB, task roles, Dockerfile |

---

## Sizing a Fargate Task

### Little's Law

```
N = λ × W

N = concurrent requests needed
λ = throughput (req/s)
W = average response time (seconds)
```

At 1000 req/s with 100ms average response (Redis HIT dominant):

```
N = 1000 × 0.1 = 100 concurrent slots
```

### Async FastAPI capacity per task (1 vCPU, 2 GB)

Uvicorn runs an asyncio event loop. I/O-bound handlers (Redis + Aurora) release the loop while waiting, so one worker handles far more than one request at a time.

```
Workers:           3  (rule of thumb: 2 × vCPU + 1)
DB pool per worker: 20 connections
Concurrent DB ops: 3 × 20 = 60 (Aurora constraint)
Redis: non-blocking, not the limit
Practical safe capacity: ~300 req/s at <100ms avg
```

### How to benchmark a single task

Stress-test with increasing VUs and watch for the **knee of the curve** — the point where p99 latency rises sharply while CPU approaches 100%.

```
VUs: 10 → 50 → 100 → 200 → 400
Metrics to watch per step:
  - CPU% on the task (ECS CloudWatch: CPUUtilization)
  - p50, p95, p99 from k6
  - Error rate
  - Active DB connections (Aurora: DatabaseConnections metric)

Stop: when p99 doubles from baseline, or error rate > 0.1%
Result: safe_capacity = throughput at last stable step × 0.7 (safety margin)
```

### Fleet sizing formula

```
tasks = ceil(peak_req_s / task_capacity) × 1.5  (safety factor)

At 1000 req/s peak, 300 req/s per task:
  tasks = ceil(1000 / 300) × 1.5 = ceil(3.33) × 1.5 = 4 × 1.5 ≈ 6
  Round down to 4 (minimum) with auto-scaling to 6 on CPU > 70%
```

For this newsletter API: **4 tasks** handles 1000 req/s peak with headroom.

---

## Cost Comparison

### Assumptions

| Parameter | Value | Basis |
|---|---|---|
| Lambda memory | 256 MB (0.25 GB) | `infra/template.yaml` |
| Lambda avg duration | 130 ms | 90% Redis HIT × 100ms + 10% Aurora × 400ms |
| Fargate task | 1 vCPU, 2 GB | Minimum practical for Python ASGI |
| Fargate tasks | 4 (HA + peak headroom) | Fleet sizing above |
| Region | eu-west-1 | This deployment |

### Lambda monthly cost formula

```
Monthly requests = R × 86400 × 30 = R × 2,592,000

Request cost  = R × 2,592,000 / 1,000,000 × $0.20        = R × $0.5184
Compute cost  = R × 2,592,000 × 0.13s × 0.25 GB
                × $0.0000166667 / GB-s                    = R × $1.404

Lambda total  = R × $1.9224 / month
```

### Fargate monthly cost formula

```
Per task/month = (1 vCPU × $0.04048/h + 2 GB × $0.004445/h) × 730h
              = ($0.04048 + $0.00889) × 730 = $36.04

Fixed (4 tasks + ALB base):
  4 × $36.04 + $11.68 (ALB base)  = $155.84/month

Variable (ALB LCU, ~1 LCU per 200 req/s):
  R / 200 × $5.84/LCU/month       = R × $0.0292/month

Fargate total = $155.84 + R × $0.0292 / month
```

### At 1000 req/s peak

```
Lambda:  1000 × $1.9224            = $1,922/month
Fargate: $155.84 + 1000 × $0.0292 = $185/month

Ratio: Lambda is 10× more expensive
```

---

## Crossover Point

Break-even where Lambda cost equals Fargate cost (2-task minimum for HA):

```
Fixed Fargate (2 tasks):  2 × $36.04 + $11.68 = $83.76/month

R × $1.9224 = $83.76 + R × $0.0292
R × ($1.9224 − $0.0292) = $83.76
R × $1.8932 = $83.76
R ≈ 44 req/s
```

**Lambda becomes more expensive than Fargate at ~44 req/s sustained.**

### Cost at key thresholds

| Sustained req/s | Lambda/month | Fargate/month | Ratio |
|---|---|---|---|
| 10 | $19 | $87 | Fargate 4.6× **more** expensive |
| 44 | $85 | $85 | **Break-even** |
| 100 | $192 | $87 | Lambda 2.2× more expensive |
| 200 | $385 | $90 | Lambda 4.3× more expensive |
| 500 | $961 | $100 | Lambda 9.6× more expensive |
| 1000 | $1,922 | $185 | Lambda 10.4× more expensive |

```
Cost ($)
2000 │  Lambda ╱
     │        ╱
1500 │       ╱
     │      ╱
1000 │     ╱
     │    ╱
 500 │   ╱ ← crossover ~44 req/s
     │  ╱╌╌╌╌╌╌ Fargate (nearly flat)
   0 └──────────────────────────── req/s
     0    200   400   600   800  1000
```

---

## Decision Guide

### Choose Lambda when

- Traffic is sporadic or unpredictable (pay-per-request is cheaper below ~44 req/s average)
- Bursts are infrequent and short (cold start tax is a one-time cost per burst)
- Zero ops overhead is a requirement (no ECS, no ALB, no Docker)
- Development/staging environments with low traffic

### Choose Fargate when

- Sustained throughput exceeds ~44 req/s
- p99 latency consistency is required (cold starts are unacceptable)
- DB connection pooling matters (Lambda burns connections at scale)
- Traffic pattern is predictable enough to right-size a fleet

### For this newsletter API at production scale

10M users × 5 reads/day = 578 req/s average, 1000 req/s peak.  
This is **13× above the crossover point**. Fargate is the correct production choice.

Lambda remains correct for Phase 1 (proving the API, passing load tests cheaply). The handlers, cache layer, and response builders port directly to FastAPI routes with minimal changes. Lambda is phase-1 infrastructure, not a design mistake.

---

## Related

- `docs/troubleshooting/2026-05-09-k6-newsletter-cached-500-errors.md` — throttle investigation and warm-up implementation
- `infra/template.yaml` — current Lambda SAM configuration
