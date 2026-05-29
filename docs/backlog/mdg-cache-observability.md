# MDG Cache Observability

Cache response headers and load-test bypass support for the PHP MDG component. The Python newsletter module has both; neither was ported to MDG when the Symfony service was built.

---

## Background

The Python newsletter module returns `X-Lambda-Cache: HIT|MISS` on every response. k6 reads this header to split latency metrics by cache source (`req_by_cache{cache:HIT}` vs `req_by_cache{cache:MISS}`). It also supports `X-Bypass-Cache: 1` (env-gated) to route requests directly to the DB, making the uncached load test measure true Aurora latency instead of Redis.

The PHP MDG `CacheService` does cache get/set correctly, but returns no observable signal — k6 sees a flat latency distribution with no way to distinguish Redis hits from DB queries. There is also no bypass path, so an MDG-targeted uncached load test is currently impossible.

Reference: [load-test-cache-isolation.md](load-test-cache-isolation.md) — Option A rationale (implemented for Python, not MDG).

---

## Items

### 1. `X-Cache: HIT|MISS` response header in PHP MDG

**What:** `CacheService::get()` currently returns the cached value or `null`. Extend it to also return a cache-source signal. Each controller adds an `X-Cache` header to the `JsonResponse` based on that signal.

**How to implement:**

1. `CacheService::get()` returns a result object (or the existing value + a bool flag) indicating HIT or MISS.

2. Each controller sets the header:
   ```php
   $response = new JsonResponse($result);
   $response->headers->set('X-Cache', $cacheHit ? 'HIT' : 'MISS');
   return $response;
   ```

3. Header name `X-Cache` (not `X-Lambda-Cache`) — the Lambda prefix no longer applies; update `load_tests/newsletter/summary.js` `CACHE_HEADER` constant accordingly (see item 3 below).

**Tests to add:**
- Cache hit path returns `X-Cache: HIT`
- Cache miss path returns `X-Cache: MISS`

**Status:** Open

---

### 2. `X-Bypass-Cache: 1` support in `CacheService` (env-gated)

**What:** When env var `APP_ALLOW_CACHE_BYPASS=true` and the incoming request carries `X-Bypass-Cache: 1`, `CacheService` skips both `get` and `set`. Requests go straight to the DB. The env var gate ensures bypass is impossible in production.

**How to implement:**

1. Read the flag once at container build time (constructor injection or `$_ENV` check):
   ```php
   private bool $bypassAllowed;

   public function __construct(...) {
       $this->bypassAllowed = ($_ENV['APP_ALLOW_CACHE_BYPASS'] ?? 'false') === 'true';
   }
   ```

2. Thread the request through to `CacheService` — either pass the `Request` object or a resolved bool from the controller:
   ```php
   $bypass = $this->bypassAllowed && $request->headers->get('X-Bypass-Cache') === '1';
   ```

3. Wrap cache calls:
   ```php
   if (!$bypass) {
       $cached = $this->cache->get($key);
       if ($cached !== null) { return [$cached, true]; }
   }
   $result = $this->repo->find(...);
   if (!$bypass) { $this->cache->set($key, $result); }
   return [$result, false];
   ```

4. Add `APP_ALLOW_CACHE_BYPASS=true` to the MDG Fargate task definition for `dev` only (never `prod`). Terraform variable already exists for the Python service — add equivalent for MDG.

**Tests to add:**
- Bypass header + env true → DB called, cache not read, cache not written
- Bypass header + env false → cache used normally (security guard)
- No bypass header → cache used normally

**Status:** Open

---

### 3. Update k6 load tests to read `X-Cache` from MDG responses

**What:** `load_tests/newsletter/summary.js` currently uses `CACHE_HEADER = "X-Lambda-Cache"`. Once MDG returns `X-Cache`, update the constant and verify the cache breakdown table in k6 output works correctly.

**Dependency:** Requires item 1 above.

**How to implement:**

1. Change `summary.js`:
   ```js
   export const CACHE_HEADER = "X-Cache";
   ```

2. Verify existing `newsletter_cached.js`, `newsletter_uncached.js`, and `mixed_realistic.js` still produce the HIT/MISS breakdown in k6 summary output.

3. When MDG-specific k6 scenarios are added (`load_tests/mdg/`), reuse `summary.js` helpers — same header, same breakdown logic.

**Status:** Open
