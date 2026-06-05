# Run Migrations and Fixtures Locally

Start the stack, migrate the schema, load fixture data.

---

## 1. Start the stack

```bash
docker-compose up -d
```

## 2. Run migrations

```bash
cd mdg && php bin/console doctrine:migrations:migrate --no-interaction
```

## 3. Load fixtures

```bash
php bin/console doctrine:fixtures:load --no-interaction
```

> **Warning:** `doctrine:fixtures:load` purges the database before loading. All existing rows are deleted.

---

## Override DB connection

Migrations and fixtures read `DB_HOST`, `DB_PASSWORD`, and `REDIS_URL` from the environment.
Set them in `mdg/.env.local` (gitignored) or export them before running the commands above.
