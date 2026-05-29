# Backlog

Improvements and automation gaps identified during active development. Not bugs — things that work but should be hardened or automated.

---

## Index

| # | File | Area | Items | Status |
|---|------|------|-------|--------|
| 1 | [ci-cd-automation.md](ci-cd-automation.md) | CI/CD | Post-deploy smoke test, `sam local invoke` in CI, unit tests in CI, build output validation, CloudWatch error check | Closed |
| 2 | [load-test-cache-isolation.md](load-test-cache-isolation.md) | Load testing | Cache-bypass header (Option A, implemented), short TTL stack (B, rejected), sequential ID pool (C, rejected) | Closed |
| 3 | [mdg-api-key-auth.md](mdg-api-key-auth.md) | MDG security | API key header auth between FastAPI and MDG (deferred from ADR-005) | Open |
| 4 | [php-code-quality.md](php-code-quality.md) | PHP quality | PHPStan static analysis, PHP CS Fixer formatting | Open |
| 5 | [php-ci-automation.md](php-ci-automation.md) | PHP CI | Doctrine migrations in GitHub Actions before PHPUnit | Open |
| 6 | [mdg-cache-observability.md](mdg-cache-observability.md) | MDG caching | `X-Cache: HIT\|MISS` response header, `X-Bypass-Cache` bypass, k6 tracking | Open |
| 7 | [observability-logging.md](observability-logging.md) | Observability | Replace `print()` in Python scripts, add Monolog to PHP MDG | Open |

---

## Open Items

| # | Item | File | Priority |
|---|------|------|----------|
| 3.1 | API key header auth on MDG (Symfony listener + FastAPI httpx header) | [mdg-api-key-auth.md](mdg-api-key-auth.md) | Low — implement when second caller appears or audit log required |
| 4.1 | PHPStan static analysis at level 5+ | [php-code-quality.md](php-code-quality.md) | Medium — catches type errors and unsafe calls before CI |
| 4.2 | PHP CS Fixer with PSR-12 ruleset | [php-code-quality.md](php-code-quality.md) | Low — formatting consistency |
| 5.1 | Run `doctrine:migrations:migrate` in GitHub Actions before PHPUnit | [php-ci-automation.md](php-ci-automation.md) | High — tests against stale schema fail unexpectedly |
| 6.1 | `X-Cache: HIT\|MISS` response header in PHP MDG controllers | [mdg-cache-observability.md](mdg-cache-observability.md) | High — without it, k6 cannot split MDG latency by cache source |
| 6.2 | `X-Bypass-Cache: 1` support in `CacheService` (env-gated) | [mdg-cache-observability.md](mdg-cache-observability.md) | High — needed for MDG uncached load test to measure true DB latency |
| 6.3 | Update k6 load tests to read `X-Cache` from MDG responses | [mdg-cache-observability.md](mdg-cache-observability.md) | Medium — depends on 6.1 |
| 7.1 | Replace `print()` with `logging` module in Python scripts | [observability-logging.md](observability-logging.md) | Medium — no log levels or structured output today |
| 7.2 | Add Monolog structured logging to PHP MDG | [observability-logging.md](observability-logging.md) | Low — no logging instrumentation today |

---

## Closed Items

| # | Area | File | Reason closed |
|---|------|------|---------------|
| 1 | CI/CD automation | [ci-cd-automation.md](ci-cd-automation.md) | pytest in `fargate-deploy.yml`; smoke test (curl /health) in deploy workflow; SAM items obsolete after Fargate migration |
| 2 | Load test cache isolation | [load-test-cache-isolation.md](load-test-cache-isolation.md) | Option A (`X-Bypass-Cache`) implemented in Python newsletter module |

---

## How to Add Items

1. Create or update a file in this directory (one file per area)
2. Add a row to the Index table above
3. Add rows to Open Items for each new item
4. When an item ships, move its row from Open Items to Closed Items and update the Index Status
