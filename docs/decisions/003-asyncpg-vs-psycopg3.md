# ADR-003: asyncpg as Async PostgreSQL Driver for Fargate

**Date:** 2026-05-13  
**Status:** Accepted  
**Author:** Marco Ganassin

---

## Context

ADR-002 decided to migrate the compute layer from Lambda to Fargate (async FastAPI). The current `src/db.py` uses **psycopg2** — a synchronous DBAPI2 driver that blocks the event loop on every query. It cannot be used as-is in an asyncio-based service.

Two async PostgreSQL drivers are mature enough for production:

1. **asyncpg** — pure async, Cython-compiled, binary protocol by default
2. **psycopg3** (package: `psycopg[binary]`) — async + sync API, DBAPI2-compatible successor to psycopg2

The newsletter API runs raw SQL (no ORM), uses a connection pool sized at 20 connections per worker, and must sustain 1,000 req/s at p99 < 300ms (uncached path).

---

## Options Considered

### Option 1 — psycopg3 async

Async mode of psycopg3 (`psycopg.AsyncConnection`, `psycopg_pool.AsyncConnectionPool`). Keeps `%s` placeholder syntax and `Row` objects that behave like dicts, minimising diff from psycopg2.

**Rejected because:**

- **Lower throughput:** ~13,000 queries/s per connection vs asyncpg's ~20,000. At 1,000 req/s this is not a bottleneck, but it translates to ~35% higher CPU per DB operation — relevant on a 1 vCPU task.
- **Binary protocol is opt-in:** Must pass `binary=True` per query or per connection. asyncpg uses binary protocol by default, removing one runtime configuration footgun.
- **Async support is newer:** psycopg3 async reached stability later than asyncpg; fewer production asyncio/FastAPI reference architectures exist for it.
- **psycopg_pool is a separate package:** adds a dependency and a version-pin to manage alongside the driver itself.

### Option 2 — asyncpg (chosen)

Designed from the ground up for asyncio. Uses PostgreSQL binary protocol by default. Connection pool is built into the package (`asyncpg.create_pool`). Cython-compiled core.

**Chosen because:**

- **Highest throughput:** ~20,000 q/s per connection in benchmarks; ~1.5× faster than psycopg3 async in pure query throughput.
- **Binary protocol default:** integer/UUID/timestamp values transfer as fixed-width bytes, not ASCII strings. Lower CPU per row at any query volume.
- **Purpose-built for asyncio:** no sync-wrapper layer, no internal thread pool, zero event-loop blocking by design.
- **Mature connection pool:** `asyncpg.create_pool` has been in production since 2017; timeout, max_inactive_connection_lifetime, and health-check parameters are battle-tested.
- **FastAPI ecosystem:** the canonical FastAPI + PostgreSQL pattern uses asyncpg; community examples, debugging resources, and library integrations (e.g. Databases, Encode ORM) target it.

**Trade-off accepted:** placeholder syntax changes from `%s` to `$1, $2, …`. This is a one-time migration confined to `src/db.py` and query strings in handlers.

---

## Decision

Use **asyncpg** with `asyncpg.create_pool` for the Fargate service. The pool is initialised once at application startup (FastAPI `lifespan` event) and injected into handlers via FastAPI dependency injection.

Connection sizing follows ADR-002: 3 Uvicorn workers per task × 20 connections per worker = 60 concurrent DB connections per task. With 4 tasks: 240 total backend connections, within Aurora Serverless v2 and RDS Proxy limits.

---

## Usage

### Pool initialisation (FastAPI lifespan)

```python
from contextlib import asynccontextmanager
import asyncpg
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await asyncpg.create_pool(
        host=os.environ[EnvVar.DB_HOST],
        port=int(os.environ.get(EnvVar.DB_PORT, "5432")),
        database=os.environ[EnvVar.DB_NAME],
        user=os.environ[EnvVar.DB_USER],
        password=os.environ[EnvVar.DB_PASSWORD],
        min_size=5,
        max_size=20,
        command_timeout=5,
    )
    yield
    await app.state.db.close()

app = FastAPI(lifespan=lifespan)
```

### Query pattern (handler)

```python
# asyncpg returns asyncpg.Record objects — convert to dict where needed
async with request.app.state.db.acquire() as conn:
    row = await conn.fetchrow(
        "SELECT * FROM newsletters WHERE newsletter_id = $1", newsletter_id
    )
if row is None:
    return not_found("newsletter")
return ok(dict(row))
```

### Placeholder migration from psycopg2

```python
# psycopg2 (old)
cursor.execute("SELECT * FROM newsletters WHERE newsletter_id = %s", (newsletter_id,))

# asyncpg (new)
row = await conn.fetchrow("SELECT * FROM newsletters WHERE newsletter_id = $1", newsletter_id)
```

---

## Consequences

- **Placeholder migration:** all SQL strings must use `$N` positional parameters. A global search for `%s` in handlers will surface every query to update.
- **No DBAPI2 cursor:** asyncpg does not have a cursor. Use `fetchrow` (one row), `fetch` (list of rows), `fetchval` (scalar), `execute` (no result). `asyncpg.Record` converts to `dict` via `dict(row)`.
- **Binary protocol:** transparent performance gain; no operational impact. RDS Proxy supports binary protocol.
- **RDS Proxy compatibility:** asyncpg works with RDS Proxy in transaction-mode. Avoid `SET` statements or session-scoped state outside transactions — RDS Proxy may route subsequent queries to a different backend connection.
- **Testing:** `asyncpg.Record` is not JSON-serialisable directly. Mock queries must return `dict` objects (or `asyncpg.Record` equivalents). `unittest.mock.AsyncMock` covers `fetchrow` / `fetch` with standard `return_value`.
