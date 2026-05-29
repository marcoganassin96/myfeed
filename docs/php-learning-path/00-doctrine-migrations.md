# Doctrine Migrations

## Why

Migrations keep code and database in sync as a project evolves.

- Share schema changes via git — teammates run `migrate`, get exact same DB state
- Deploy schema changes atomically alongside code
- Roll back consistently via `down()` if a deploy fails

## Version Control

Doctrine tracks applied migrations in the `doctrine_migration_versions` table.
Each migration file is a timestamped class (eg: `Version20260528152601`) with:
- `up()` — apply changes
- `down()` — revert changes (used for rollback)

## Workflow

```bash
# 1. Check current status
php bin/console doctrine:migrations:status

# 2. Generate migration from entity diff
php bin/console doctrine:migrations:diff
# Opens migrations/VersionYYYYMMDDHHMMSS.php — review up() SQL before running

# 3. Preview SQL without executing
php bin/console doctrine:migrations:migrate --dry-run

# 4. Run migration
php bin/console doctrine:migrations:migrate

# 5. Verify all executed
php bin/console doctrine:migrations:status
# "New Migrations: 0" = success

# 6. Spot-check migration recorded
php bin/console doctrine:query:sql "SELECT * FROM doctrine_migration_versions"

# 7. Spot-check table exists
php bin/console doctrine:query:sql "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"
```

## Reset (local dev only)

```bash
# Wipe schema
php bin/console doctrine:query:sql "DROP SCHEMA public CASCADE; CREATE SCHEMA public"

# Delete old migration file, regenerate
rm migrations/VersionXXX.php
php bin/console doctrine:migrations:diff
php bin/console doctrine:migrations:migrate
```

> Only use schema drop on local Docker DB — irreversible.
