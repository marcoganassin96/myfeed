# Spec: Doctrine Migrations + Fixtures

**Date:** 2026-05-27
**Status:** Approved

---

## Context

The database schema is currently managed by raw SQL files (`migrations/001_initial_schema.sql`, `migrations/002_deep_dives.sql`) applied by the Python seed script (`newsletter/scripts/00_seed.py`). Mock data is inserted by the same Python script. The `mdg` Symfony service has Doctrine ORM but no migrations or fixtures bundle.

Goal: move schema ownership and mock data seeding into Doctrine (migrations + fixtures) within the `mdg` service.

---

## Scope

- Schema DDL → `doctrine:migrations:diff`-generated migration class
- Mock seed data → `doctrine:fixtures:load` via `LoadMockData` fixture
- New Python script `00_seed_doctrine.py` that invokes Doctrine commands, queries IDs, saves seed result
- Old `00_seed.py` kept untouched; deprecated once `00_seed_doctrine.py` is validated end-to-end

---

## Architecture

### 1. New Dependencies (`mdg/composer.json`)

```json
"require": {
    "doctrine/doctrine-migrations-bundle": "^3.3"
},
"require-dev": {
    "doctrine/doctrine-fixtures-bundle": "^3.6"
}
```

Bundle registration in `mdg/config/bundles.php`:

```php
Doctrine\Bundle\MigrationsBundle\DoctrineMigrationsBundle::class => ['all' => true],
Doctrine\Bundle\FixturesBundle\DoctrineFixturesBundle::class => ['dev' => true],
```

New config `mdg/config/packages/doctrine_migrations.yaml`:

```yaml
doctrine_migrations:
    migrations_paths:
        'DoctrineMigrations': '%kernel.project_dir%/migrations'
    storage:
        table_storage:
            table_name: 'doctrine_migration_versions'
```

---

### 2. New Entity Classes

All entities are read-only (getters only), matching the existing `Newsletter` entity style. No Doctrine-managed UUID generation — DB handles it via `gen_random_uuid()` defaults added manually after diff.

| Class | Table | PK |
|---|---|---|
| `Topic` | `topics` | `topic_id` UUID |
| `Thread` | `threads` | `thread_id` UUID |
| `NewsEvent` | `news_events` | `event_id` UUID |
| `EventThreadMembership` | `event_thread_memberships` | composite (`event_id`, `thread_id`) |
| `NewsletterEvent` | `newsletter_events` | composite (`newsletter_id`, `event_id`) |
| `NewsletterContextLink` | `newsletter_context_links` | `id` UUID |

Files: `mdg/src/Entity/{Topic,Thread,NewsEvent,EventThreadMembership,NewsletterEvent,NewsletterContextLink}.php`

---

### 3. Schema Migration

**Generate:**
```bash
cd mdg && php bin/console doctrine:migrations:diff
```

Output: `mdg/migrations/Version<timestamp>.php`

**Manual post-generation edits** — add `gen_random_uuid()` defaults to all UUID PKs:
```php
$this->addSql("ALTER TABLE topics ALTER COLUMN topic_id SET DEFAULT gen_random_uuid()");
$this->addSql("ALTER TABLE threads ALTER COLUMN thread_id SET DEFAULT gen_random_uuid()");
$this->addSql("ALTER TABLE news_events ALTER COLUMN event_id SET DEFAULT gen_random_uuid()");
$this->addSql("ALTER TABLE newsletters ALTER COLUMN newsletter_id SET DEFAULT gen_random_uuid()");
$this->addSql("ALTER TABLE newsletter_context_links ALTER COLUMN id SET DEFAULT gen_random_uuid()");
$this->addSql("ALTER TABLE interactions ALTER COLUMN interaction_id SET DEFAULT gen_random_uuid()");
```

Also add the `pgcrypto` extension creation at the top of `up()`:
```php
$this->addSql("CREATE EXTENSION IF NOT EXISTS pgcrypto");
```

**Run:**
```bash
php bin/console doctrine:migrations:migrate --no-interaction
```

Root `migrations/*.sql` files are kept for reference but no longer applied by any script once this migration is in place.

---

### 4. Fixture Class

**File:** `mdg/src/DataFixtures/LoadMockData.php`

Implements `FixtureInterface`. Uses `$em->getConnection()->executeStatement()` for bulk inserts — no per-row `persist()` calls.

**Data volumes:**

| Insert | Count |
|---|---|
| Topics | 3 (technology, politics, sports) |
| Threads | 15 (5 per topic) |
| NewsEvents | 300 (20 per thread) |
| EventThreadMemberships | 300 (1 per event, chained previous_event_id) |
| Newsletters | 90 (1 per topic × 30 days) |
| NewsletterEvents | 450 (5 events per newsletter) |
| NewsletterContextLinks | ~176 (sliding window of 2, starting at index 2) |
| Subscriptions | 2000 (1000 mock users × 2 topics) |
| Interactions | 10000 (cycling 3 types across 100 events × 1000 users) |

Insert page size: 300–500 rows per batch to match Python `execute_values` page sizes.

**Run:**
```bash
php bin/console doctrine:fixtures:load --no-interaction
```

`--no-interaction` drops and reloads all fixture data (TRUNCATE + insert). No `--append` flag — fixtures are always a clean reset.

---

### 5. New Python Seed Script

**File:** `newsletter/scripts/00_seed_doctrine.py`

**Flow:**

1. Run schema migration:
   ```
   docker compose exec mdg php bin/console doctrine:migrations:migrate --no-interaction
   ```
   (local) or ECS task override (dev/prod, same SSM tunnel pattern)

2. Run fixtures:
   ```
   docker compose exec mdg php bin/console doctrine:fixtures:load --no-interaction
   ```

3. Query DB directly (psycopg2, same connection logic as old script) for generated IDs:
   - `SELECT topic_id FROM topics ORDER BY name`
   - `SELECT newsletter_id, topic_id, date FROM newsletters ORDER BY topic_id, date`

4. Save `out/{env}/seed_result.json` — **identical format** to old script so `01_prewarm.py` and `03_get_load_test_ids.py` require no changes.

**Env var:** `USE_DOCTRINE_SEED=1` in pipeline to select this script. Old `00_seed.py` remains default until validated.

---

## Testing

- After `doctrine:migrations:migrate`: all 8 tables exist, `doctrine_migration_versions` row present
- After `doctrine:fixtures:load`: row counts match table above
- After `00_seed_doctrine.py`: `out/local/seed_result.json` present and parseable by `01_prewarm.py`
- PHPUnit: no new unit tests needed for the fixture itself (data correctness verified by integration counts)

---

## Out of Scope

- Removing old `00_seed.py` (happens after validation)
- Removing root `migrations/*.sql` files (kept for reference)
- Adding Doctrine relations / associations between entities (not needed — repositories use raw queries)
- Running fixtures in prod (dev only)
