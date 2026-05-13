# Tunnel Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace scattered config functions and duplicate context managers in `scripts/tunnel.py` with a `ServiceConfig` dataclass, a `Service` StrEnum, and a single `ssm_tunnel(service)` context manager that reads local tunnel ports from config.

**Architecture:** `Service(StrEnum)` owns config resolution — each member's value matches its config section key (`"database"` / `"redis"`), so `_cfg()[service]` resolves directly. `ServiceConfig` is pure data. One `ssm_tunnel(service, host=None)` replaces both old context managers. Four callers change import + call site only — no logic change.

**Tech Stack:** Python 3.12, `dataclasses`, `enum.StrEnum`, `psycopg2`, `redis-py`, AWS SSM CLI

**Spec:** `docs/superpowers/specs/2026-05-07-tunnel-refactor-design.md`

---

## Files

| Action | Path | Change |
|--------|------|--------|
| Modify | `config/dev.yaml` | Add `local_port` under `database` and `redis` |
| Modify | `config/local.yaml` | Add `local_port` under `database` and `redis` |
| Rewrite | `scripts/tunnel.py` | `ServiceConfig` + `Service` + single `ssm_tunnel` |
| Modify | `scripts/00_seed.py` | Import `Service`; `ssm_tunnel()` → `ssm_tunnel(Service.DB)` |
| Modify | `scripts/03_get_load_test_ids.py` | Import `Service`; `ssm_tunnel()` → `ssm_tunnel(Service.DB)` |
| Modify | `scripts/pipeline.py` | Import `Service`; `ssm_tunnel()` → `ssm_tunnel(Service.DB)` |
| Modify | `scripts/01_prewarm.py` | Replace `ssm_redis_tunnel` import/call with `ssm_tunnel(Service.REDIS)` |

> **No unit tests for `scripts/tunnel.py`** — it wraps subprocess + network I/O; no mock infrastructure exists for it. Verification is manual (see Task 3).

---

## Task 1: Add `local_port` to config files

**Files:**
- Modify: `config/dev.yaml`
- Modify: `config/local.yaml`

- [ ] **Step 1: Add `local_port` to `config/dev.yaml`**

Replace the `database` and `redis` sections:

```yaml
database:
  host: "newsletter-dev-postgres.cjyo8yc62lie.eu-west-1.rds.amazonaws.com"
  port: 5432
  local_port: 15432
  name: "newsletter"
  user: "newsletter"

redis:
  host: "newsletter-dev-redis-oxij5h.serverless.euw1.cache.amazonaws.com"
  port: 6379
  local_port: 16379
  ssl: true
```

- [ ] **Step 2: Add `local_port` to `config/local.yaml`**

Replace the `database` and `redis` sections:

```yaml
database:
  host: "localhost"
  port: 5432
  local_port: 15432
  name: "newsletter"
  user: "newsletter"

redis:
  host: "localhost"
  port: 6379
  local_port: 16379
  ssl: false
```

- [ ] **Step 3: Commit**

```bash
git add config/dev.yaml config/local.yaml
git commit -m "chore(config): add local_port for SSM tunnel to db and redis config"
```

---

## Task 2: Rewrite `scripts/tunnel.py`

**Files:**
- Rewrite: `scripts/tunnel.py`

- [ ] **Step 1: Replace the full contents of `scripts/tunnel.py`**

```python
#!/usr/bin/env python3
"""
Shared SSM port-forwarding context manager for scripts that need DB/Redis access.

Usage:
    from tunnel import ssm_tunnel, Service

    with ssm_tunnel(Service.DB) as (host, port):
        conn = psycopg2.connect(host=host, port=port, ...)

    with ssm_tunnel(Service.REDIS) as (host, port):
        rc = redis.Redis(host=host, port=port, ssl=True, ssl_cert_reqs=None, ...)

Behaviour:
    - BASTION_ID set (env or Terraform output) → opens SSM tunnel to remote host:port
      on 127.0.0.1:<local_port>, yields ("127.0.0.1", local_port), kills tunnel on exit.
    - No bastion found → yields (remote_host, remote_port) unchanged.
"""
import contextlib
import os
import pathlib
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import StrEnum

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from config import load as _cfg

TIMEOUT_S = 30

_ENV_PREFIXES = {"database": "DB", "redis": "REDIS"}


@dataclass
class ServiceConfig:
    name: str
    host: str
    remote_port: int
    local_port: int


class Service(StrEnum):
    DB = "database"
    REDIS = "redis"

    def config(self, host_override: str | None = None) -> "ServiceConfig":
        section = _cfg()[str(self)]
        env_prefix = _ENV_PREFIXES[str(self)]
        host = host_override or os.environ.get(f"{env_prefix}_HOST") or section["host"]
        remote_port = int(os.environ.get(f"{env_prefix}_PORT") or section["port"])
        return ServiceConfig(
            name=str(self),
            host=host,
            remote_port=remote_port,
            local_port=section["local_port"],
        )


def _aws_region() -> str:
    return os.environ.get("AWS_REGION") or _cfg()["aws"]["region"]


def _get_bastion_id() -> str | None:
    bid = os.environ.get("BASTION_ID", "").strip()
    if bid:
        return bid
    tf_dir = pathlib.Path(__file__).parent.parent / "terraform" / "envs" / "dev"
    if tf_dir.exists():
        result = subprocess.run(
            ["terraform", f"-chdir={tf_dir}", "output", "-raw", "bastion_instance_id"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return None


def _start(bastion_id: str, remote_host: str, remote_port: int, local_port: int) -> subprocess.Popen:
    params = (
        f'{{"host":["{remote_host}"],'
        f'"portNumber":["{remote_port}"],'
        f'"localPortNumber":["{local_port}"]}}'
    )
    proc = subprocess.Popen(
        [
            "aws", "ssm", "start-session",
            "--region", _aws_region(),
            "--target", bastion_id,
            "--document-name", "AWS-StartPortForwardingSessionToRemoteHost",
            "--parameters", params,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"  SSM tunnel started (pid {proc.pid}) → localhost:{local_port}", file=sys.stderr)
    return proc


def _wait(proc: subprocess.Popen, local_port: int, timeout: int = TIMEOUT_S):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"SSM process exited early (code {proc.returncode}) "
                f"— port {local_port} may already be in use"
            )
        try:
            with socket.create_connection(("127.0.0.1", local_port), timeout=1):
                print("  Tunnel ready.", file=sys.stderr)
                return
        except OSError:
            time.sleep(1)
    raise TimeoutError(f"Tunnel not ready after {timeout}s")


def _kill(proc: subprocess.Popen):
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    print("  Tunnel closed.", file=sys.stderr)


@contextlib.contextmanager
def ssm_tunnel(service: Service, host: str | None = None):
    cfg = service.config(host)
    bastion_id = _get_bastion_id()

    if not bastion_id:
        yield cfg.host, cfg.remote_port
        return

    print(f"  Bastion: {bastion_id}", file=sys.stderr)
    proc = _start(bastion_id, cfg.host, cfg.remote_port, cfg.local_port)
    try:
        _wait(proc, cfg.local_port)
        yield "127.0.0.1", cfg.local_port
    finally:
        _kill(proc)
```

- [ ] **Step 2: Verify import resolves (no bastion path)**

```bash
cd scripts && python -c "from tunnel import ssm_tunnel, Service; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add scripts/tunnel.py
git commit -m "refactor(tunnel): ServiceConfig dataclass + Service enum + single ssm_tunnel"
```

---

## Task 3: Update callers

**Files:**
- Modify: `scripts/00_seed.py`
- Modify: `scripts/03_get_load_test_ids.py`
- Modify: `scripts/pipeline.py`
- Modify: `scripts/01_prewarm.py`

- [ ] **Step 1: Update `scripts/00_seed.py`**

Change line 19:
```python
# before
from tunnel import ssm_tunnel
# after
from tunnel import ssm_tunnel, Service
```

Change line 213:
```python
# before
with ssm_tunnel() as (db_host, db_port):
# after
with ssm_tunnel(Service.DB) as (db_host, db_port):
```

- [ ] **Step 2: Update `scripts/03_get_load_test_ids.py`**

Change line 26:
```python
# before
from tunnel import ssm_tunnel
# after
from tunnel import ssm_tunnel, Service
```

Change line 72:
```python
# before
with ssm_tunnel() as (host, port):
# after
with ssm_tunnel(Service.DB) as (host, port):
```

- [ ] **Step 3: Update `scripts/pipeline.py`**

Change line 26:
```python
# before
from tunnel import ssm_tunnel  # noqa: E402
# after
from tunnel import ssm_tunnel, Service  # noqa: E402
```

Change line 60:
```python
# before
with ssm_tunnel() as (host, port):
# after
with ssm_tunnel(Service.DB) as (host, port):
```

- [ ] **Step 4: Update `scripts/01_prewarm.py`**

Change line 17:
```python
# before
from tunnel import ssm_redis_tunnel
# after
from tunnel import ssm_tunnel, Service
```

Change line 75:
```python
# before
with ssm_redis_tunnel() as (r_host, r_port):
# after
with ssm_tunnel(Service.REDIS) as (r_host, r_port):
```

- [ ] **Step 5: Confirm old symbols are gone**

```bash
grep -r "ssm_redis_tunnel\|from tunnel import ssm_tunnel$" scripts/
```

Expected: no output (all callers now import both `ssm_tunnel` and `Service`).

- [ ] **Step 6: Run full test suite (no regressions in src/)**

```bash
pytest tests/ -v
```

Expected: all tests pass, zero failures, zero new skips.

- [ ] **Step 7: Commit**

```bash
git add scripts/00_seed.py scripts/01_prewarm.py scripts/03_get_load_test_ids.py scripts/pipeline.py
git commit -m "refactor(scripts): update callers to ssm_tunnel(Service.*)"
```

---

## Manual Verification Checklist (post-implementation)

Run after all tasks are committed. No bastion path only requires local Docker.

```bash
# 1. Local path — no tunnel opened, completes without error
env=local python scripts/01_prewarm.py

# 2. Dev path (requires AWS credentials + bastion running)
# DB tunnel opens on localhost:15432 (not 5432)
env=dev python scripts/00_seed.py

# 3. Dev path — Redis tunnel opens on localhost:16379 (not 6379)
env=dev python scripts/01_prewarm.py
```
