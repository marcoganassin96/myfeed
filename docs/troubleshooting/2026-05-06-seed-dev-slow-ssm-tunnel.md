# Seed script extremely slow over SSM tunnel (dev env)

**Date:** 2026-05-06  
**Environment:** `dev` (Aurora RDS t3.micro via SSM tunnel)  
**Script:** `scripts/00_seed.py`  
**Status:** Under investigation

---

## Symptom

Full seed run takes ~800 s over SSM tunnel; same script on local Docker completes in ~11 s.
Redis pre-warm step times out (`✗ Timeout connecting to server`) because the tunnel is still alive but ElastiCache is unreachable after the long DB phase.

### Timing comparison

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

---

## Root cause (hypothesis)

SSM tunnel adds per-round-trip latency (~50–150 ms typical). `00_seed.py` inserts rows one-by-one (or in small batches) inside a Python loop, so every `INSERT` becomes a separate round trip amplified by tunnel latency.

Local Docker: round-trip ≈ 0 ms → no amplification.  
SSM tunnel: round-trip ≈ 50–150 ms → 10 000 interactions × ~50 ms = ~500 s.

---

## Confirmed facts

- Script runs to completion locally (Docker Compose, PostgreSQL 16).
- Script completes over SSM tunnel but takes 799 s total.
- Redis pre-warm fails with `✗ Timeout connecting to server` — ElastiCache VPC endpoint only accessible from inside the VPC; the SSM tunnel forwards only the RDS port, not Redis.
- Bastion instance: `i-01aca106a1c356f0c`

---

## Potential fixes

### 1. Batch inserts (highest impact)
Replace per-row `INSERT` loops with `executemany` or `COPY`-style bulk inserts.  
Expected: reduce round trips from N to ~1 per table → local-like performance over tunnel.

### 2. Run seed from inside VPC (eliminates tunnel)
SSH/SSM into bastion, run seed from there → zero tunnel overhead, Redis reachable directly.  
Downside: requires packaging the script or copying it to the bastion.

### 3. Separate Redis pre-warm from seed
Run Redis pre-warm as a Lambda function or from inside VPC where ElastiCache is reachable.  
Needed regardless of fix chosen for DB inserts.

---

## Next steps

- [ ] Profile `00_seed.py` insert loops — identify which use per-row vs batch
- [ ] Rewrite hot loops (interactions, subscriptions) to use `executemany` or `psycopg2.extras.execute_values`
- [ ] Decide whether Redis pre-warm should be a separate in-VPC step
