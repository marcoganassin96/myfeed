# Seed script extremely slow over SSM tunnel (dev env)

**Date:** 2026-05-06  
**Environment:** `dev` (Aurora RDS t3.micro via SSM tunnel)  
**Script:** `scripts/00_seed.py`  
**Status:** Partially resolved (DB inserts fixed; Redis pre-warm open)

---

## Step 0: Problem statement

### Symptom

Full seed run takes ~800 s over SSM tunnel; same script on local Docker completes in ~11 s.
Redis pre-warm step times out (`✗ Timeout connecting to server`) because the tunnel is still alive but ElastiCache is unreachable after the long DB phase.

#### Timing comparison

| Step | Local (Docker) | Dev (SSM tunnel) |
|---|---|---|
| Truncate | 0.11 s | 0.06 s |
| topics (3) | 0.00 s | 0.14 s |
| threads (15) | 0.02 s | 0.70 s |
| news_events (300) | 0.48 s | 28.22 s |
| newsletters (90) | 0.43 s | 26.12 s |
| context_links | 0.14 s | 8.29 s |
| subscriptions (1 000 × 2) | 1.50 s | 95.61 s |
| interactions (10 000) | 8.66 s | **488.95 s** |
| Redis pre-warm | 0.06 s | 126.29 s (timeout) |
| **Total** | **11.48 s** | **799.50 s** |

The `interactions` insert alone is 489 s — roughly 56× slower than local.

### Root cause (hypothesis)

SSM tunnel adds per-round-trip latency (~50–150 ms typical). `00_seed.py` inserts rows one-by-one (or in small batches) inside a Python loop, so every `INSERT` becomes a separate round trip amplified by tunnel latency.

Local Docker: round-trip ≈ 0 ms → no amplification.  
SSM tunnel: round-trip ≈ 50–150 ms → 10 000 interactions × ~50 ms = ~500 s.

### Confirmed facts

- Script runs to completion locally (Docker Compose, PostgreSQL 16).
- Script completes over SSM tunnel but takes 799 s total.
- Redis pre-warm fails with `✗ Timeout connecting to server` — ElastiCache VPC endpoint only accessible from inside the VPC; the SSM tunnel forwards only the RDS port, not Redis.
- Bastion instance: `i-01aca106a1c356f0c`

### Potential fixes

#### 1. Batch inserts (highest impact)
Replace per-row `INSERT` loops with `executemany` or `COPY`-style bulk inserts.  
Expected: reduce round trips from N to ~1 per table → local-like performance over tunnel.

#### 2. Run seed from inside VPC (eliminates tunnel)
SSH/SSM into bastion, run seed from there → zero tunnel overhead, Redis reachable directly.  
Downside: requires packaging the script or copying it to the bastion.

#### 3. Separate Redis pre-warm from seed
Run Redis pre-warm as a Lambda function or from inside VPC where ElastiCache is reachable.  
Needed regardless of fix chosen for DB inserts.

### Next steps

- [x] Profile `00_seed.py` insert loops — identify which use per-row vs batch
- [x] Rewrite hot loops (interactions, subscriptions) to use `executemany` or `psycopg2.extras.execute_values`
- [ ] Decide whether Redis pre-warm should be a separate in-VPC step


---


## UPDATE 1 (2026-05-06) - Fix batch inserts ✓ DONE
- **Problem**: insertion operations take too much time: intolerable latency of 800 s total + interruption of Redis pre-warm step due to tunnel timeout.
- **Cause**: N `INSERT` statements executed in a loop, leading to N ssm tunnel round trips, each amplified by tunnel latency (~50 ms)
- **Solution**: perform bulk inserts for all tables
    - Replaced all per-row `INSERT` loops with `execute_values` bulk inserts.  
    - For tables requiring RETURNING (topics, threads, news_events, newsletters): used `fetch=True` to get IDs back in insertion order.  
    - Page sizes: 300 for events/memberships, 500 for newsletter_events/context_links, 1000 for subscriptions/interactions.
- **Result**: DB seed time 799 s → ~17 s over SSM tunnel (47× speedup).

### After fix — timing comparison (2026-05-06)

| Step | Local (Docker) | Dev before fix | Dev after fix |
|---|---|---|---|
| Truncate | 0.11 s | 0.06 s | 0.07 s |
| topics (3) | 0.00 s | 0.14 s | 0.14 s |
| threads (15) | 0.02 s | 0.70 s | 0.08 s |
| news_events (300) | 0.48 s | 28.22 s | **0.27 s** |
| newsletters (90) | 0.43 s | 26.12 s | **0.24 s** |
| context_links | 0.14 s | 8.29 s | **0.09 s** |
| subscriptions (1 000 × 2) | 1.50 s | 95.61 s | **0.33 s** |
| interactions (10 000) | 8.66 s | 488.95 s | **1.85 s** |
| Redis pre-warm | 0.06 s | 126.29 s (timeout) | 126.31 s (timeout — open) |
| **Total** | **11.48 s** | **799.50 s** | **143.39 s** |

DB seed time: 799 s → ~17 s (47× speedup). Remaining 126 s is Redis pre-warm timeout (separate issue).  
Commit: `refactor(seed): replace per-row inserts with execute_values bulk inserts`


### Remaining open issue

#### Redis pre-warm timeout (126 s)

ElastiCache VPC endpoint is not reachable from outside the VPC. The SSM tunnel forwards only the RDS port; Redis connection always times out.

**Options:**
- Use a new ssm tunnel between local machine and bastion (already in use to communicate with RDS instance) that forwards to Redis ports.
- Run Redis pre-warm as a Lambda invoked post-seed (Redis reachable from VPC)
- Run seed from inside VPC via SSM session on bastion (eliminates tunnel entirely, Redis reachable directly)
- Skip pre-warm for dev — cold cache acceptable if load tests handle first-request latency

### Next steps
- [x] Implement and verify effectiveness of using a new ssm tunnel for Redis pre-warm, recycling the same bastion instance as relay.
- [x] Split seed and pre-warm into separate scripts to allow independent execution and avoid coupling Redis pre-warm with DB seed performance.

---

## UPDATE 2 (2026-05-07) - Redis SSM tunnel: connection timeout ✗ FAILED → fix pending

### Symptom

`01_prewarm.py` hangs indefinitely on `rc.flushall()` in dev env. Local execution completes without errors. SSM tunnel establishes successfully (`Tunnel ready.`) but no Redis command ever returns.

### Diagnostic

Added `socket_timeout=10` / `socket_connect_timeout=10` to the Redis client and replaced `flushall()` with `rc.ping()` as first command to isolate whether the hang was a Redis command restriction or a connection-level failure.

Result after diagnostic change:
`ping()` timed out after exactly 10 s — TCP connection to ElastiCache via bastion never established. Not a Redis command restriction: the connection itself failed.

### Root cause

ElastiCache security group (`aws_security_group.redis`) only allows inbound port 6379 from Lambda SG. Bastion SG has no egress rule for port 6379 and Redis SG has no ingress rule from Bastion SG. Contrast with Aurora, which has both rules wired explicitly.

| | Aurora (port 5432) | ElastiCache (port 6379) |
|---|---|---|
| Lambda → SG | ✓ | ✓ |
| Bastion → SG ingress | ✓ `aurora_from_bastion` rule | ✗ missing |
| Bastion SG egress | ✓ port 5432 → aurora_sg | ✗ missing |

### Next steps

- [ ] Mirror Aurora SG pattern for Redis in `terraform/modules/bastion/`: add egress rule port 6379 → `var.redis_sg_id` to bastion SG; add `aws_security_group_rule.redis_from_bastion` (ingress on redis SG from bastion SG); add `redis_sg_id` variable; wire `redis_sg_id = module.vpc.redis_sg_id` in `terraform/envs/dev/main.tf`
- [ ] Run `terraform apply` in `terraform/envs/dev` to deploy SG rule changes
- [ ] Re-run `01_prewarm.py` — verify connection succeeds and `flushall()` returns without timeout
- [ ] If `flushall()` fails with Redis error (not timeout): ElastiCache Serverless may not support the command — replace with key-by-key SET pipeline (TTL overwrite is sufficient)
