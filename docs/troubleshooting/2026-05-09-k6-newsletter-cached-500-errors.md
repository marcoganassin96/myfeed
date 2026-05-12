# Troubleshooting: Load Tests Failing at Trivial Load

**Date:** 2026-05-09  
**Environment:** `newsletter-api-dev`, region `eu-west-1`  
**Status:** Root cause identified — fix pending

---

## Problem

`newsletter_cached` — the scenario designed to test Redis-served responses at scale — fails with HTTP 500 at just 20 VUs over 5 seconds:

```
http_req_failed: 10.18%  45 out of 442 requests
✗ 200           ↳  89% — ✓ 397 / ✗ 45
```

Failures cluster at the start of the run and taper off after ~2 seconds. This should be an easy scenario. Something is fundamentally wrong before we even reach scale.

---

## Why It Was Hard to Debug

k6 reports aggregate HTTP status codes. A 500 looks the same whether:

- Lambda received the request and Redis threw an SSL error
- Lambda received the request, Redis missed, and Aurora failed on cold start
- API Gateway rejected the request before Lambda ran at all

All three return `{"message": "Internal server error"}`. Without knowing which path each request took, every hypothesis is equally plausible and none can be ruled out.

CloudWatch investigation made it worse: querying for ERROR logs in the test window returned no results — either the timestamp was off, or the 500s came from API Gateway directly (no Lambda invocation = no Lambda log).

The investigation stalled because the core question — *did this request reach Redis or not?* — had no answer in the data.

---

## Root Cause

**The prewarm writes 3 Redis keys. k6 uses 20 IDs. 85% of requests miss the cache on every run.**

`00_seed.py` seeds **90 newsletters** into Aurora (3 topics × 30 days).

`01_prewarm.py` warms Redis with this loop:

```python
for tid in payload.topic_ids:
    nl_id = payload.nl_ids.get(f"{tid}|{latest_date_str}")  # latest date only
    if nl_id:
        pipe.set(f"newsletter:{nl_id}", ...)
```

One key per topic, for the single latest date → **3 keys** written.

`03_get_load_test_ids.py` fetches k6's working set:

```sql
SELECT newsletter_id FROM newsletters LIMIT 20
```

No date filter → pulls across all 30 days → **20 IDs**, most from dates not in Redis.

| | Count |
|---|---|
| Aurora rows | 90 |
| Redis keys after prewarm | **3** |
| k6 IDs | 20 |
| k6 IDs with a Redis key | ≤ 3 |
| k6 IDs that miss cache → Aurora | **≥ 17 (85%)** |

`newsletter_cached` is therefore exercising the **Aurora cold start path** on 85% of its requests. Lambda has no RDS Proxy on this free-tier environment, so concurrent cold starts compete for connections and some fail → 500.

The scenario name was misleading: it was never testing cache performance.

---

## Plan

Two independent activities fix this. They can be done in either order but both are required before re-running at scale.

---

### Activity 1 — Cache Tracing

**Problem:** k6 has no visibility into whether a request was served from Redis or Aurora. All 500s look identical.

**What to build:**

**`X-Lambda-Cache` response header** — `src/handlers/newsletters.py` sets:
- `X-Lambda-Cache: HIT` when the response comes from Redis
- `X-Lambda-Cache: MISS` when it falls through to Aurora

Named `X-Lambda-Cache` (not `X-Cache`) to avoid CloudFront overwriting it.

If no `X-Lambda-Cache` header is present, API Gateway returned the error before Lambda was invoked.

**`req_by_cache` k6 Trend metric** — all newsletter load test scripts record:

```javascript
const reqByCache = new Trend("req_by_cache", true);

reqByCache.add(res.timings.duration, {
  cache: res.headers["X-Lambda-Cache"] || "NONE",
  ok: res.status > 0 && res.status < 400 ? "1" : "0",
});
```

**Cache breakdown table** — `04_run_load_tests.py` parses k6's JSON output (`--out json=...`) and prints after each scenario:

```
  Cache breakdown:
  Source         Reqs    OK%   Fail%   Avg ms   OK avg  Fail avg
  ----------------------------------------------------------------
  Redis (HIT)   10234   99.8%   0.2%     14.2     13.8     423.1
  Aurora (MISS)   142   85.2%  14.8%     87.6     61.4     312.5
```

**Diagnostic key:**

| Pattern | Likely cause |
|---|---|
| Failures on `NONE` | API GW throttle — Lambda never invoked |
| Failures on `MISS`, high `Fail avg` | Aurora cold start failure |
| Failures on `HIT`, high `Fail avg` | Redis SSL / socket timeout |
| `MISS` count unexpectedly high for `newsletter_cached` | Prewarm incomplete |

**Files to change:** `src/fields.py`, `src/handlers/newsletters.py`, `src/response.py`, all `load_tests/*.js`, `scripts/04_run_load_tests.py`.

---

### Activity 2 — Progressive Pipeline

**Problem:** The current pipeline is not coherent. Setup scripts and k6 scenarios are decoupled, execution order is wrong, and there are no hard gates between steps.

**Current state — incoherent order:**

```
scripts/pipeline.py:
  00_seed.py                 ← data setup
  01_prewarm.py              ← Redis warm (silently partial)
  02_create_test_tokens.py   ← Cognito tokens
  03_get_load_test_ids.py    ← ID fetch

04_run_load_tests.py:
  1. newsletter_cached  500 VUs   ← Redis expected but 85% miss
  2. newsletter_cold    200 VUs   ← cachebuster has no effect at Lambda level
  3. deep_dive_sse       50 VUs
  4. mixed_realistic   1000 VUs
  5. cold_start_stress 0→1000 VUs
```

Three specific problems:

- **Cached scenario runs before Aurora is validated.** If it fails, can't tell if Aurora or Redis is the culprit.
- **`newsletter_cold.js` uses `?_cb=Date.now()`.** This bypasses API Gateway response caching only. Lambda's Redis cache is keyed on `newsletter:{id}` with no query string — prewarmed IDs still return `X-Cache: HIT`. The cold scenario is misnamed.
- **No guard between prewarm and cached scenario.** If prewarm writes fewer keys than expected (as it does: 3 of 90), the cached test silently becomes an Aurora test. No warning is printed.

**Target state — single `pipeline.py` with progressive steps:**
- seed      # 00_seed.py
- tokens    # 02_create_test_tokens.py
- ids       # 03_get_load_test_ids.py
- smoke     # k6: smoke.js (1 VU, all endpoints)
- cold      # k6: newsletter_cold.js (Redis still empty)
- prewarm   # 01_prewarm.py + coverage assertion
- cached    # k6: newsletter_cached.js
- sse       # k6: deep_dive_sse.js
- mixed     # k6: mixed_realistic.js
- stress    # k6: cold_start_stress.js

Run from a specific step: `python scripts/pipeline.py --from-step prewarm`

Key properties:
- Every step is a hard gate — non-zero exit stops the pipeline.
- `COLD` runs before `PREWARM`, so Redis is genuinely empty for that scenario. Remove the `?_cb=` cachebuster from `newsletter_cold.js`.
- `PREWARM` asserts `redis_key_count == len(seed_result.nl_ids)` before the pipeline continues.
- `SMOKE` (new `load_tests/smoke.js`) runs before any load test: 1 VU, one request per endpoint, generous thresholds — verifies the API is up and all routes return expected status codes.

---

## Checkpoint — 2026-05-12

### Activity 1 completed

Cache tracing is now live:

- `X-Lambda-Cache` response header (renamed from `X-Cache` to avoid CloudFront collision)
- `cacheCount` Counter + `req_by_cache` Trend in all k6 scripts
- `summary.js` prints a per-source breakdown table at end of each run

### First run with tracing — 20 VUs / 5s / 90/90 Redis coverage

```
  Cache breakdown:
  Source           Reqs     OK%   Fail%   OK avg  Fail avg
  ──────────────────────────────────────────────────────────
  Redis (HIT)       374  100.0%    0.0%     87ms       —
  Aurora (MISS)      23  100.0%    0.0%    581ms       —
  No header          75    0.0%  100.0%      —        93ms

  http_req_failed: 15.88% (75/472)
```

Errors cluster in the first ~1s of the run (31 of 75 fail before `running (02.0s)`), then taper off sharply.

### Revised root cause

**The original hypothesis was wrong.** Aurora is not causing the failures.

| Source | Requests | Failure rate |
|---|---|---|
| Redis (HIT) | 374 | **0%** |
| Aurora (MISS) | 23 | **0%** |
| No `X-Lambda-Cache` header | 75 | **100%** |

Every single failure is in the `NONE` bucket — requests that returned 500 with no Lambda-Cache header. Per the diagnostic key in Activity 1: **Lambda was not invoked for these requests**. API Gateway returned the error before the handler ran.

The 93ms fail-avg rules out API Gateway timeout (which would be multi-second). It points to Lambda cold starts during initial burst: the first wave of concurrent invocations triggers container initialisation, and before the containers are ready, API Gateway returns 500.

Evidence consistent with cold-start throttle:
- Failures cluster at t=0–1s (burst onset), then zero errors from t=2s onward
- No failures on HIT or MISS paths (those hit already-warm containers)
- 93ms response time is consistent with API GW error response, not Lambda execution

### What this changes

The Aurora connection problem is not the failure path at this load. At 20 VUs the Aurora path succeeds (avg 581ms, 0% error). The blocker is Lambda concurrency during the initial burst.

### Remaining work

Activity 2 (progressive pipeline) is still required before re-running at scale — the pipeline rewrite adds a smoke step, correct ordering (COLD before PREWARM), and the coverage assertion gate. After that, the NONE failures need a dedicated investigation:

- Check Lambda reserved concurrency limit in `infra/template.yaml`
- Check CloudWatch for `Throttles` metric during the burst window
- Consider provisioned concurrency for the newsletter handler if throttles are confirmed

---

## Related

- `docs/troubleshooting/2026-05-08-lambda-missing-psycopg2-k6-all-checks-failed.md` — prior incident in same environment
- `docs/backlog/ci-cd-automation.md` — item 1.1: post-deploy smoke test would have caught this earlier
