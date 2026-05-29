# Observability — Logging

Replace ad-hoc `print()` statements in Python scripts and add structured logging to PHP MDG. Currently neither component has log levels, structured output, or a consistent logging interface.

---

## Items

### 1. Replace `print()` with `logging` module in Python scripts

**What:** Python scripts in `newsletter/scripts/` use `print(..., file=sys.stderr)` for progress output. Replace with the standard `logging` module: `StreamHandler(sys.stderr)`, `INFO` for progress, `WARNING`/`ERROR` for failures.

**Why:** `print()` provides no log levels, no filtering, and no structured output. Replacing with `logging` enables level-based filtering (e.g., suppress INFO in CI), and is the standard interface for Python observability tooling.

**Affected files:**
- `newsletter/scripts/pipeline.py` — step banners, runtime summary, pipeline complete
- `newsletter/scripts/run_load_tests.py` — scenario headers, results table, API URL
- `newsletter/scripts/flush_redis.py` — confirmation message
- `newsletter/scripts/scale_down.py` — scale confirmation
- `newsletter/scripts/03_get_load_test_ids.py` — ID count confirmation

**How to implement:**

1. Add to each script (or a shared `scripts/utils.py`):
   ```python
   import logging
   logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                       format="%(levelname)s %(message)s")
   logger = logging.getLogger(__name__)
   ```

2. Replace `print(f"...", file=sys.stderr)` with `logger.info(...)` (progress) or `logger.error(...)` (failures).

3. Scripts that exit on error: replace `print(f"ERROR: ...", file=sys.stderr); sys.exit(1)` with `logger.error(...); sys.exit(1)`.

**Status:** Open

---

### 2. Add Monolog structured logging to PHP MDG

**What:** The PHP MDG Symfony service has no logging instrumentation. Add `symfony/monolog-bundle` and log cache hits/misses at `DEBUG` level, errors at `ERROR` level from service classes.

**Why:** No visibility into cache behaviour or errors beyond what Symfony's error handler surfaces. With Monolog, ECS log driver captures structured output to CloudWatch without any additional infrastructure.

**How to implement:**

1. Add to `mdg/composer.json`:
   ```json
   "require": {
       "symfony/monolog-bundle": "^3.10"
   }
   ```

2. Register bundle in `mdg/config/bundles.php`:
   ```php
   Symfony\Bundle\MonologBundle\MonologBundle::class => ['all' => true],
   ```

3. Inject `LoggerInterface` into services that need it:
   ```php
   use Psr\Log\LoggerInterface;

   public function __construct(
       private CacheService $cache,
       private NewsletterRepository $repo,
       private LoggerInterface $logger,
   ) {}
   ```

4. Log at appropriate levels:
   ```php
   $this->logger->debug('cache hit', ['key' => $key]);
   $this->logger->debug('cache miss', ['key' => $key]);
   $this->logger->error('db query failed', ['exception' => $e->getMessage()]);
   ```

5. ECS log driver (`awslogs`) already captures stdout/stderr from the container — no additional AWS config needed.

**Status:** Open
