# Design: tunnel.py Refactor — ServiceConfig + Service Enum

**Date:** 2026-05-07
**Branch:** `feat/api-serving-layer`
**File:** `scripts/tunnel.py`

---

## Context

`tunnel.py` exposes two near-identical context managers (`ssm_tunnel`, `ssm_redis_tunnel`) whose only difference is which service config they read. Service configuration is scattered across four module-level functions (`_db_host`, `_db_port`, `_redis_host`, `_redis_port`). Local tunnel ports are hardcoded equal to remote ports, preventing use alongside a locally-running instance of the same service.

---

## Goals

1. Replace scattered config functions with a `ServiceConfig` dataclass.
2. Replace two duplicate context managers with a single generic one.
3. Read local tunnel ports from config (not hardcoded in Python).
4. Keep callers minimal: change call site only (no logic change in callers).

---

## Architecture

### `ServiceConfig` dataclass

Pure data — no logic.

```python
@dataclass
class ServiceConfig:
    name: str          # "database" | "redis" — used in log messages
    host: str
    remote_port: int   # port on the remote service (RDS / ElastiCache)
    local_port: int    # port bound on 127.0.0.1 when tunnel is open
```

### `Service` StrEnum

Value equals the config section key, so `_cfg()[service]` resolves without a lookup table.

```python
class Service(StrEnum):
    DB = "database"
    REDIS = "redis"

    def config(self, host_override: str | None = None) -> ServiceConfig:
        section = _cfg()[str(self)]
        env_prefix = {"database": "DB", "redis": "REDIS"}[str(self)]
        host = host_override or os.environ.get(f"{env_prefix}_HOST") or section["host"]
        remote_port = int(os.environ.get(f"{env_prefix}_PORT") or section["port"])
        return ServiceConfig(
            name=str(self),
            host=host,
            remote_port=remote_port,
            local_port=section["local_port"],
        )
```

Env var override behaviour (e.g. `DB_HOST`, `REDIS_PORT`) is preserved from current code.

### Single `ssm_tunnel` context manager

```python
@contextlib.contextmanager
def ssm_tunnel(service: Service, host: str | None = None):
    cfg = service.config(host)
    bastion_id = _get_bastion_id()
    if not bastion_id:
        yield cfg.host, cfg.remote_port
        return
    proc = _start(bastion_id, cfg.host, cfg.remote_port, cfg.local_port)
    try:
        _wait(proc, cfg.local_port)
        yield "127.0.0.1", cfg.local_port
    finally:
        _kill(proc)
```

`_start`, `_wait`, `_kill`, `_get_bastion_id` — unchanged.

---

## Config Changes

Add `local_port` to both config files. Only `dev.yaml` uses it in practice (SSM tunnel only opens when a bastion is found); `local.yaml` carries it for schema consistency.

**`config/dev.yaml`**
```yaml
database:
  port: 5432
  local_port: 15432

redis:
  port: 6379
  local_port: 16379
```

**`config/local.yaml`**
```yaml
database:
  port: 5432
  local_port: 15432

redis:
  port: 6379
  local_port: 16379
```

---

## Caller Changes

| File | Old | New |
|------|-----|-----|
| `scripts/00_seed.py` | `ssm_tunnel()` | `ssm_tunnel(Service.DB)` |
| `scripts/03_get_load_test_ids.py` | `ssm_tunnel()` | `ssm_tunnel(Service.DB)` |
| `scripts/pipeline.py` | `ssm_tunnel()` | `ssm_tunnel(Service.DB)` |
| `scripts/01_prewarm.py` | `ssm_redis_tunnel()` | `ssm_tunnel(Service.REDIS)` |

Import change: `from tunnel import ssm_tunnel, Service` (remove `ssm_redis_tunnel` import where present).

---

## Removed

- `ssm_redis_tunnel()` — deleted; replaced by `ssm_tunnel(Service.REDIS)`
- `_db_host()`, `_db_port()`, `_redis_host()`, `_redis_port()` — deleted; replaced by `Service.config()`

`_aws_region()` is retained (used by `_start()`).

---

## Testing

No unit tests exist for `tunnel.py` (it wraps subprocess + network). Manual verification:

1. `env=local python scripts/01_prewarm.py` — no tunnel opened, completes as before.
2. `env=dev python scripts/00_seed.py` — SSM tunnel opens on `localhost:15432`, seed completes.
3. `env=dev python scripts/01_prewarm.py` — SSM tunnel opens on `localhost:16379`, pre-warm completes.
