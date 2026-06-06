# ADR-009 — Remove ElastiCache Redis; replace with NullCacheAdapter in dev

## Context

AWS ElastiCache Serverless (Redis) was costing ~$3/day even when idle — ~$90/month for a service that was barely used during Phase 1 load testing. Redis cannot be "stopped" on ElastiCache Serverless; the only option to stop billing is deletion.

MDG's cache layer (ADR-006) is built around `RedisClientInterface`, with `PredisAdapter` as the sole concrete implementation. Deleting the ElastiCache instance without an app change would cause MDG to crash at container startup (Predis throws on failed connection).

Two environments need different behaviour after the deletion:

| Environment | Redis available? | Required behaviour |
|---|---|---|
| `local` (Docker Compose) | Yes — Redis container present | Connect via Predis, cache normally |
| `dev` (AWS Fargate) | No — ElastiCache deleted | Fall through to DB on every request |

## Options Considered

**Option A — NullCacheAdapter (chosen)**
Add a second `RedisClientInterface` implementation that discards all reads/writes. Wire it in `dev` via `config/packages/dev/services.yaml`. `local` keeps `PredisAdapter` unchanged.

- Pro: zero infra cost; one new PHP class; no DB schema change; local dev unaffected.
- Con: every MDG request in dev hits Aurora directly — acceptable because dev load is low and load tests run against real data.

**Option B — Keep Redis, downgrade instance**
Switch to a fixed-size ElastiCache node (e.g., `cache.t3.micro`).

- Rejected: still ~$15–25/month with no Phase 1 workload to justify it.

**Option C — Redis on Fargate as a sidecar**
Run Redis inside the MDG Fargate task.

- Rejected: adds container complexity; Redis state lost on every ECS task replacement; no persistence benefit at this scale.

## Decision

Delete ElastiCache Serverless. Introduce `NullCacheAdapter` and use Symfony's environment-specific DI to select the right adapter at container build time.

### How Symfony selects the adapter

```
config/
  services.yaml              # global: binds PredisAdapter as default RedisClientInterface
  packages/
    local/
      mdg.yaml               # REDIS_URL = real Docker redis URL
    dev/
      services.yaml          # overrides alias: RedisClientInterface → NullCacheAdapter
      mdg.yaml               # mdg.redis_url: '' (empty — satisfies _defaults.bind at compile time)
```

`services.yaml` (global, used by `local`):
```yaml
_defaults:
  bind:
    string $redisUrl: '%mdg.redis_url%'

App\Cache\RedisClientInterface: '@App\Cache\PredisAdapter'
```

`config/packages/dev/services.yaml` (overrides for `dev`):
```yaml
services:
    App\Cache\RedisClientInterface: '@App\Cache\NullCacheAdapter'
```

Symfony merges env-specific config on top of the global config, so `dev` gets `NullCacheAdapter` without touching `local`.

### NullCacheAdapter contract

```php
class NullCacheAdapter implements RedisClientInterface
{
    public function get(string $key): ?string { return null; }
    public function setex(string $key, int $ttl, string $value): void {}
    public function del(string ...$keys): void {}
    public function flush(): void {}
}
```

All `CacheService` callers see a cache miss on every read and a silent no-op on every write. No code outside `Cache/` changed.

## Consequences

- **Cost:** ElastiCache line item eliminated (~$90/month saved).
- **Dev performance:** MDG dev hits Aurora on every request. Acceptable — dev traffic is negligible.
- **Local dev:** unchanged. `PredisAdapter` + Docker Redis still active.
- **Future upgrade path:** to re-enable caching in dev, add ElastiCache back and remove `config/packages/dev/services.yaml`. No other code change required.
- **Orphaned module:** `terraform/modules/redis/` is no longer called from any root module. Files kept for reference; delete when confident the instance will not be restored.
