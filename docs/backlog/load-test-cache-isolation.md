# Load Test Cache Isolation

Strategies for fully separating cached vs uncached request paths in load tests, so caching improvements can be measured in isolation.

---

## Background

Current `newsletter_uncached.js` runs 200 VUs against a random pool of newsletter IDs. After the warmup phase warms the cache, almost all subsequent requests hit Redis — only 112 of 122,245 requests (0.09%) were cache misses in the first EC2 baseline run (2026-05-18).

This means:
- `newsletter_uncached.js` is effectively a second cached test, not an uncached one
- Aurora latency under real load is unknown
- Before/after comparisons for DB optimisations are impossible

Reference: [2026-05-16 load test baselines doc](../troubleshooting/2026-05-16-fargate-load-test-baselines-and-thresholds.md) §7 — Aurora MISS anomaly note.

---

## Options Considered

### Option A — Cache-bypass header (recommended)

**What:** Add `X-Bypass-Cache: 1` request header support to the newsletters handler. When present (and only when `ALLOW_CACHE_BYPASS=true` env var is set), the handler skips both `cache_get` and `cache_set`, routing every request directly to Aurora.

**Why this wins:**
- Tests the exact Aurora code path under full 200-VU concurrency — no data or infra gymnastics
- Same Fargate deployment, same ALB, same connection pool — apples-to-apples vs cached run
- Env-gated (`ALLOW_CACHE_BYPASS`) so bypass is impossible in production
- k6 change is trivial: one extra header in `newsletter_uncached.js`

**Why the others lose:**
- Option B requires a second Fargate stack with different config; two stacks drift
- Option C requires seeding 500k+ rows and cache never stabilises — hard to reason about

**How to implement:**

1. Add `ALLOW_CACHE_BYPASS` to `src/fields.py`:
   ```python
   class EnvVar(StrEnum):
       # ... existing entries ...
       ALLOW_CACHE_BYPASS = "ALLOW_CACHE_BYPASS"
   ```

2. In `src/handlers/newsletters.py`, read the flag and header:
   ```python
   import os
   from fields import EnvVar, HttpHeader

   _bypass_allowed = os.environ.get(EnvVar.ALLOW_CACHE_BYPASS, "false").lower() == "true"

   def _bypass_cache(event: dict) -> bool:
       return _bypass_allowed and event.get("headers", {}).get("X-Bypass-Cache") == "1"
   ```

3. In `get_newsletter_by_id`, wrap cache calls:
   ```python
   bypass = _bypass_cache(event)

   if not bypass:
       cached = cache.cache_get(cache_key)
       if cached:
           return ok(cached)

   row = db.fetch_newsletter(newsletter_id)
   if row is None:
       return not_found()

   if not bypass:
       cache.cache_set(cache_key, row)

   return ok(row)
   ```

4. Add `ALLOW_CACHE_BYPASS=true` to Fargate task definition only for `dev` environment (never `prod`).

5. In `load_tests/newsletter_uncached.js`, set the header:
   ```js
   const bypassHeaders = { ...headers, "X-Bypass-Cache": "1" };

   export function loadFn() {
     const id = NEWSLETTER_IDS[Math.floor(Math.random() * NEWSLETTER_IDS.length)];
     const res = http.get(`${BASE_URL}/newsletters/${id}`, { headers: bypassHeaders });
     // ... rest unchanged
   }
   ```

6. Update threshold in `newsletter_uncached.js` to reflect true Aurora latency once 3 stable bypass runs exist (current placeholder `p(99)<100` is wrong — expect ~590ms based on 112-sample EC2 estimate).

**Tests to add:**
- Handler returns 200 and hits Aurora when bypass header set + env var true
- Handler uses cache normally when env var false, even if header is sent (security guard)
- Handler uses cache normally when header absent

**Status:** Open

---

### Option B — Short TTL in a dedicated test deployment

**What:** Deploy a second Fargate stack (`newsletter-uncached-test`) with `REDIS_TTL_SECONDS=1`. Cache entries expire before any VU can re-use them → effectively 100% miss rate without code changes.

**Why rejected (for now):**
- Two stacks to maintain, diff in config makes comparisons less clean
- TTL=1s affects all requests including the warmup — can't have a mixed test (some cached, some not)
- ALB and Fargate task count may differ between stacks, introducing confounders

**Status:** Rejected in favour of Option A. Revisit if bypass header adds security complexity.

---

### Option C — Sequential large ID pool in k6

**What:** Pre-generate 200,000+ newsletter IDs in `load_tests/config.js`. k6 iterates IDs sequentially using `__VU` and `__ITER` counters so each ID is requested at most once. Cache fills but is never re-hit → ~100% miss rate with no code changes.

**Why rejected:**
- Requires seeding 200k+ rows in Aurora (seed.py currently seeds ~1,000)
- Cache memory consumption grows unbounded during test
- At 200 VUs × 15 req/s × 65s = 195,000 requests → needs almost exactly 200k unique IDs; any shortfall causes IDs to wrap and hit cache
- Hard to reason about connection pool and cache behaviour at that data scale

**Status:** Rejected. Impractical without significant seed infrastructure.

---

## What "Fully Isolated" Looks Like After Option A

| Test | Config | Expected dominant path |
|------|--------|----------------------|
| `newsletter_cached.js` | No bypass header, warm cache | 100% Redis HIT |
| `newsletter_uncached.js` | `X-Bypass-Cache: 1` header | 100% Aurora (no Redis) |
| `mixed_realistic.js` | No bypass header, random IDs | ~95% Redis HIT, ~5% MISS (natural) |

This lets you measure:
- Pure Redis latency under 500-VU load (cached test)
- Pure Aurora latency under 200-VU load (uncached test with bypass)
- Real production mix (mixed test)
