# MDG Tests

## Test Suites

| Suite | Directory | Requires running stack |
|---|---|---|
| `unit` | `Cache/`, `Controller/`, `DataFixtures/`, `Service/` | No |
| `smoke` | `Smoke/` | Yes — see prerequisites below |

---

## Running Tests

### Unit tests only (pre-commit gate)

```bash
cd mdg && composer test
```

### Smoke tests only

```bash
cd mdg && composer smoke
```

Skips cleanly with `Tests: 6, Skipped: 6` when the stack is not running.

### All tests (unit + smoke)

```bash
cd mdg && composer test:all
```

---

## Smoke Test Prerequisites

The smoke suite makes real HTTP calls against the local stack. Start the stack and load fixtures before running:

```bash
docker-compose up -d
cd mdg && php bin/console doctrine:migrations:migrate --no-interaction
cd mdg && php bin/console doctrine:fixtures:load --no-interaction
```

Default target: `http://localhost:9000`. Override with:

```bash
MDG_SMOKE_BASE_URL=http://localhost:<another-port> composer smoke
```
