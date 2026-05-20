# ADR-004: MDG Owns Schema (Single Source of Truth)

## Context

Introducing a Master Data Gateway (MDG) built on Symfony/Doctrine as an internal Fargate service. The MDG enforces multi-tenant row-level isolation and schema validation for all master data (newsletters, subscriptions, interactions). Two integration options existed for schema ownership.

## Options Considered

### Option A — MDG owns schema entirely

MDG runs Doctrine migrations; FastAPI reads master data exclusively via MDG HTTP. RDS schema is defined and evolved only through Doctrine entities.

**Chosen.**

### Option B — Bolt-on tenant layer over existing schema

FastAPI retains `migrations/001_initial_schema.sql` and direct asyncpg access. MDG adds `tenant_id` columns alongside the existing schema. Both sources must be kept in sync on every schema change.

**Rejected.**

Reasons for rejection:
- Two schema sources diverge silently — Doctrine entity and raw SQL migration can drift without compile-time detection.
- Every schema change requires atomic updates in two places; omitting one breaks either FastAPI queries or MDG queries.
- FastAPI retaining direct RDS write access bypasses Doctrine's global tenant filter, meaning multi-tenant isolation holds only if FastAPI is disciplined — not enforced by the ORM.
- Seed script (`scripts/seed.py`) and migrations become ambiguous owners of the same tables.

## Decision

Option A. MDG is the sole owner of the RDS schema.

- Doctrine entities are the canonical schema definition.
- Doctrine migrations replace `migrations/001_initial_schema.sql` for master data tables.
- FastAPI never connects directly to RDS for master data; it calls MDG over internal HTTP.
- `scripts/seed.py` is rewritten to call MDG endpoints or Doctrine fixtures — not raw SQL.
- Doctrine global filter adds `WHERE tenant_id = :current_tenant` to every query automatically.

## Usage

```
FastAPI (cache miss)
  → GET http://mdg-internal/master-data/newsletters/{id}
  → MDG resolves tenant from JWT sub
  → Doctrine query with global tenant filter applied
  → JSON response

Pipeline services (future)
  → GET http://mdg-internal/master-data/...
  → write artifacts directly to their own S3 prefix
```

Internal ALB or ECS Service Connect routes `mdg-internal` to the Symfony Fargate service. RDS Proxy sits between MDG and RDS to absorb PHP-FPM's per-worker connection overhead.

## Consequences

- **Single schema owner:** schema drift between FastAPI and MDG is impossible.
- **Tenant isolation enforced at ORM level:** no application-layer discipline required.
- **FastAPI loses direct asyncpg access** to master data tables; cache-miss latency increases by the MDG HTTP round-trip (~1–5 ms intra-VPC).
- **Cached path unchanged:** ElastiCache still serves hot reads with no MDG involvement.
- **`migrations/001_initial_schema.sql` deprecated** for master data tables; kept only for reference until MDG migrations are validated in dev.
- **RDS Proxy required:** PHP-FPM opens one connection per worker; without the proxy, connection count spikes under load.
