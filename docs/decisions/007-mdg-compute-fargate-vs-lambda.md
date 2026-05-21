# ADR-007: MDG Compute — Fargate vs Lambda, PHP-FPM vs FrankenPHP

**Date:** 2026-05-21  
**Status:** Accepted  
**Author:** Marco Ganassin

---

## Context

MDG is a PHP 8.4 / Symfony 7 service called internally by FastAPI on every user-facing request. It owns Aurora PostgreSQL and ElastiCache Redis.

Two infrastructure tiers are in scope:

- **Free tier (current):** RDS PostgreSQL `db.t3.micro` (~110 max connections), no RDS Proxy
- **Premium tier (future):** Aurora Serverless v2 + RDS Proxy (connection multiplexing)

The question: should MDG run on **Lambda** or **Fargate**? And within Fargate, should the PHP runtime be **PHP-FPM** (traditional) or **FrankenPHP** (worker mode)?

The MDG Dockerfile originally used `php -S 0.0.0.0:9000` — PHP's built-in single-threaded development server. This is unsuitable for any production load and is replaced in both options below.

---

## Options Considered

### Option 1 — Lambda + Bref (free tier)

[Bref](https://bref.sh) provides a PHP Lambda layer with a Symfony-compatible FPM runtime. Each Lambda invocation handles one HTTP request; PHP process dies after the request completes.

**Rejected for free tier because:**

- **VPC cold starts:** MDG needs Aurora and Redis, both VPC-only. Lambda VPC cold start is 0.5–1 s even with Hyperplane ENIs. Newsletter p99 targets (<50–150 ms) cannot absorb this on an internal hop.
- **Connection exhaustion:** Lambda scales by spawning instances, each opening a dedicated DB connection. `db.t3.micro` supports ~110 connections. At 200 concurrent VUs the limit is hit, producing 500 errors — same failure mode documented in ADR-002 for Lambda vs Fargate.
- **Internal latency overhead:** Lambda invocation adds ~1–5 ms per call. Multiplied across every FastAPI → MDG hop this degrades newsletter p99.

---

### Option 2 — Lambda + Bref + RDS Proxy + Provisioned Concurrency (premium tier)

With RDS Proxy, N Lambda instances share a small pool of real DB connections — connection exhaustion is solved. With provisioned concurrency, Lambda instances are pre-warmed — cold starts are eliminated for the provisioned unit count.

**Considered but not chosen for premium tier because:**

- **Cost parity:** Provisioned concurrency charges per GB-second regardless of traffic, the same economic model as Fargate. The pay-per-use advantage of Lambda disappears the moment you provision warmth.
- **Overflow still cold-starts:** Provisioned concurrency only covers the configured baseline. Any traffic spike beyond that triggers cold Lambda instances — occasional p99 spikes that are hard to bound. Fargate auto-scaling launches new tasks alongside already-warm ones; existing tasks continue serving during scale-out.
- **No throughput advantage:** Each Lambda invocation still re-runs Symfony's kernel bootstrap and DI container compilation (unless using Bref's preloading — which helps but does not match a persistent worker). FrankenPHP worker mode on Fargate boots Symfony **once** and serves all requests from memory. See the FrankenPHP section below.
- **Bref dependency:** Extra runtime layer to maintain, pin, and upgrade. Fargate uses a standard PHP Docker image.

**Where Lambda + Bref is the right choice for PHP:**
- Async/event-driven workloads triggered by SQS, S3, EventBridge
- Very low or highly variable traffic (< 1M requests/month, or 0 for long periods)
- Workloads where Symfony is not involved and bootstrap cost is negligible

---

### Option 3 — Fargate + PHP-FPM (free tier, chosen)

PHP-FPM runs a configurable pool of PHP worker processes. Each worker handles one request at a time then recycles (or stays alive for N requests, configurable via `pm.max_children` and `max_requests`). Multiple workers = concurrent request handling.

```dockerfile
FROM php:8.4-fpm-alpine
```

**Chosen for free tier because:**

- Always-warm tasks; no cold starts.
- `pm.max_children` directly controls the DB connection count — with `pm.max_children = 10` per task, 2 tasks = 20 DB connections, well within `db.t3.micro` limits.
- Consistent sub-10 ms internal latency once warm.
- No external runtime dependency (standard upstream Docker image).
- Matches the existing newsletter Fargate pattern; operational consistency.

**Limitation:** Symfony DI container is rebuilt on each FPM worker startup (not per request — workers are reused for `max_requests` cycles). Opcache keeps compiled bytecode in memory but the container graph is re-instantiated per worker process. This is the standard PHP-FPM behaviour and acceptable for the free tier.

---

### Option 4 — Fargate + FrankenPHP Worker Mode (premium tier, chosen)

#### What is FrankenPHP?

[FrankenPHP](https://frankenphp.dev) is a PHP application server written in Go, built on top of the [Caddy](https://caddyserver.com) web server. It embeds the PHP interpreter as a Go library and can run PHP applications in two modes:

1. **Traditional mode** — behaves like PHP-FPM: one PHP execution per request, process recycles.
2. **Worker mode** — the application boots once and enters a request-handling loop. The PHP process stays alive, the Symfony DI container stays in memory, and requests are dispatched to it without re-bootstrapping.

Worker mode makes PHP behave like Node.js or Go: the application initialises once and handles many requests from a single persistent process.

```dockerfile
FROM dunglas/frankenphp:php8.4-alpine
COPY . /app
CMD ["frankenphp", "run", "--config", "/etc/caddy/Caddyfile", "--worker", "public/index.php"]
```

Symfony requires `symfony/runtime` with `APP_RUNTIME=\Runtime\FrankenPhpSymfony\Runtime` and careful stateless request handling (see consequences).

#### FrankenPHP vs Traditional PHP-FPM — comparison

| Dimension | PHP-FPM | FrankenPHP Worker Mode |
|---|---|---|
| DI container | Re-instantiated per worker startup | In-memory, reused across all requests |
| Opcache | Bytecode cached | Bytecode cached + objects cached |
| Requests/s (Symfony) | ~500–1 000 req/s (2 tasks, 10 workers each) | ~2 000–5 000 req/s (same hardware) — 2–5× gain |
| Memory per request | Higher (each worker has full container) | Lower (container shared, only request data per call) |
| Code complexity | Standard PHP: global state is safe | Worker mode: global/static state persists between requests — must be explicitly reset |
| Symfony support | Mature, default | Supported via `symfony/runtime`; requires review of stateful services |
| Built-in HTTP features | None (needs nginx/apache in front) | HTTP/2, HTTP/3, TLS, early hints (via Caddy) |
| Debugging | Standard | Harder: process state persists, bugs may surface only after N requests |
| Production maturity | Very mature | Stable since 1.0 (2023); production-proven at smaller scale than FPM |

#### When to use FrankenPHP vs PHP-FPM

**Use FrankenPHP worker mode when:**
- High throughput is required (internal hot-path services, load-test targets)
- The application is stateless per request (no static caches, no request-scoped singletons leaking state)
- The team can enforce the worker-mode contract: every service that holds request-scoped data must implement `__destruct` or be registered with Symfony's `kernel.reset` event
- Premium compute tier — the performance gain justifies the complexity uplift

**Use PHP-FPM when:**
- Application correctness is the priority and global-state hygiene is uncertain
- Standard Symfony application with third-party bundles not yet audited for worker mode
- Lower traffic where 500 req/s per task is sufficient
- Simpler ops: restart a worker = kill a process; no shared state to corrupt

**For MDG specifically:** Free tier uses PHP-FPM. Premium upgrade path switches the Dockerfile base image to FrankenPHP and adds the worker mode configuration. The MDG codebase is intentionally small (3 controllers, 3 services) — stateless audit is straightforward.

---

## Decision

| Tier | Runtime | Rationale |
|---|---|---|
| Free (current) | Fargate + PHP-FPM | Connection budget control; always-warm; no cold starts; db.t3.micro safe |
| Premium (future) | Fargate + FrankenPHP worker mode | 2–5× throughput improvement; matches load test targets; RDS Proxy removes connection concern |

Lambda is not used for MDG in either tier. It remains appropriate for async/event-driven PHP workloads (SQS consumers, S3 triggers) where the request-living model is a feature, not a constraint.

---

## Consequences

**PHP-FPM (free tier):**
- Set `pm.max_children = 10`, `pm.max_requests = 500` in `www.conf`
- 2 Fargate tasks × 10 workers = 20 DB connections — within `db.t3.micro` budget
- No Symfony code changes required

**FrankenPHP worker mode (premium upgrade):**
- Replace Dockerfile base: `FROM dunglas/frankenphp:php8.4-alpine`
- Add `symfony/runtime` and `runtime/frankenphp-symfony` Composer packages
- Set env var `APP_RUNTIME=\Runtime\FrankenPhpSymfony\Runtime`
- Audit all Symfony services for request-scoped state leaks:
  - Services holding request data in properties must implement `kernel.reset`
  - No static caches that accumulate across requests
- Add `frankenphp.Caddyfile` config to the repository
- Cost: RDS Proxy is required (worker mode keeps persistent DB connections per process; proxy multiplexes them)

**CI/CD:** No change. Both options use the same Docker-based deploy pipeline.

---

## Lessons Learned

**The "PHP is slow for concurrency" mental model is outdated.**

PHP's reputation for poor concurrency performance comes from two compounding factors: (1) the request-living model forces DI container re-bootstrap on every request, and (2) PHP-FPM's process-per-request model limits per-instance concurrency to the worker pool size. Both factors are solved independently — FrankenPHP eliminates (1), and horizontal Fargate scaling eliminates (2). A Symfony app on FrankenPHP running on two Fargate tasks can sustain 2 000–5 000 req/s with p99 < 10 ms, competitive with Node.js or Go microservices at the same memory allocation.

**Lambda's "pay-per-use" advantage is an illusion for always-hot internal services.**

Lambda costs nothing when idle and scales automatically — genuine advantages for spiky or infrequent workloads. But an internal service that is called on every user-facing request is never idle in practice. The moment you add provisioned concurrency to eliminate cold starts, you pay for idle capacity — the same model as Fargate. At that point Fargate wins on latency predictability (no overflow cold-start risk), operational simplicity (no Bref layer), and throughput ceiling (FrankenPHP worker mode). Lambda's strengths are real; they just do not apply to this specific use case.

**Connection count is the first constraint to model when choosing compute for a DB-backed service.**

Both Lambda (connection-per-instance) and PHP-FPM (connection-per-worker) open real TCP connections to PostgreSQL. On `db.t3.micro` (~110 max connections), this becomes the binding constraint before CPU or memory. Modelling the connection budget — workers × tasks × safety margin — must happen before the compute decision, not after.
