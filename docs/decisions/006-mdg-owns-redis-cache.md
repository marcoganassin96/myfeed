# ADR-006: Redis Cache Ownership — MDG, Not FastAPI

## Context

FastAPI currently manages Redis directly: on every request it checks the cache, falls back to RDS on miss, and writes the result back. When MDG (Master Data Gateway) is introduced as the authoritative data layer, two services would share ownership of the same cached data.

The split causes a distributed cache invalidation problem: whenever MDG writes or updates a record in RDS, FastAPI's Redis entries become stale. MDG has no reliable way to notify FastAPI which keys to drop — doing so would require MDG to call back into FastAPI (circular dependency) or FastAPI to poll for changes (eventual consistency with no clear trigger).

## Options Considered

### Option A — FastAPI keeps Redis, MDG notifies on write

MDG exposes a `POST /cache/invalidate` endpoint. After every write, MDG calls FastAPI to evict affected keys.

**Rejected.** Creates a circular dependency (FastAPI → MDG → FastAPI). Adds a second failure mode: a failed invalidation call leaves stale data silently. Every new write path in MDG must remember to call the invalidation endpoint.

### Option B — FastAPI keeps Redis, shared TTL only

No invalidation protocol. Both services respect a short TTL (e.g., 30s) and stale reads are accepted.

**Rejected.** Acceptable for read-heavy static data, not for a master data service where writes must be immediately consistent. Also still requires FastAPI to know Redis key structure used by MDG.

### Option C — MDG owns Redis (chosen)

FastAPI makes HTTP calls to MDG. MDG handles all cache read/write/invalidation internally. FastAPI has no Redis client for DB-backed data.

**Chosen.** Cache and data live in the same service. Invalidation is a local function call, not a distributed protocol.

## Decision

MDG owns the Redis cache for all database-backed data. FastAPI is a pure HTTP consumer of MDG — it does not hold a Redis connection for DB data.

Cache flow inside MDG:

```
FastAPI  →  MDG
              ├─ Redis HIT  → return cached value
              └─ Redis MISS → query RDS → write cache → return value
```

Write flow inside MDG:

```
FastAPI  →  MDG (write endpoint)
              ├─ persist to RDS
              └─ invalidate / update Redis key  ← local call, no coordination needed
```

FastAPI's `cache_async.py` / `get_redis()` dependency is removed from all DB-data handlers. It remains available for future non-DB caching (see Lessons Learned).

## Lessons Learned (2026-05-20)

- **Cache invalidation locality is not obvious until you introduce a second service.** The moment MDG was introduced, the existing FastAPI-owns-cache model created a circular invalidation dependency. Moving ownership to the data service eliminated the problem before it was ever implemented.
- **FastAPI's Redis connection is not wasted.** Removing it from DB-data handlers does not prevent a future `get_redis()` dependency for non-DB data: rate limiting, session tokens, feature flags, or any ephemeral key not tied to MDG writes. The infrastructure stays; the scope narrows.
- **The performance cost is bounded and acceptable.** Every cache HIT now travels FastAPI → MDG (internal VPC, ~0.5–2 ms) instead of FastAPI → Redis directly. For the p99 < 50 ms load test target this overhead is negligible, and the architectural cleanliness outweighs it.
