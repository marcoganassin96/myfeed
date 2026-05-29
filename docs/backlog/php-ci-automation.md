# PHP CI Automation

Automation gaps in the MDG GitHub Actions workflow.

---

## Background

`mdg-fargate-deploy.yml` runs PHPUnit tests but does not apply Doctrine migrations before them. Tests that depend on schema state will either fail against a stale schema or pass silently against an incorrect one. This is the same class of problem that caused the 2026-05-08 Python incident — environment divergence that only surfaces under load or after a schema change.

Reference: [2026-05-08 incident](../troubleshooting/2026-05-08-lambda-missing-psycopg2-k6-all-checks-failed.md)

---

## Items

### 1. Run Doctrine migrations in GitHub Actions before PHPUnit

**What:** Add a PostgreSQL service container to the `test` job in `.github/workflows/mdg-fargate-deploy.yml`. Before running `phpunit`, apply all pending Doctrine migrations against that test DB.

**Why:** Without migrations running in CI, the test DB schema is whatever was last manually applied. A migration that works locally but wasn't run in CI will make tests pass locally and fail (or worse, silently pass) in CI.

**How to implement:**

1. Add PostgreSQL service to the test job:
   ```yaml
   services:
     postgres:
       image: postgres:16
       env:
         POSTGRES_USER: mdg
         POSTGRES_PASSWORD: mdg
         POSTGRES_DB: mdg_test
       ports:
         - 5432:5432
       options: >-
         --health-cmd pg_isready
         --health-interval 5s
         --health-timeout 5s
         --health-retries 5
   ```

2. Set `APP_ENV=test` and provide `DATABASE_URL` pointing to the service container.

3. Add migration step before `phpunit`:
   ```yaml
   - name: Run migrations
     working-directory: mdg
     env:
       DATABASE_URL: postgresql://mdg:mdg@localhost:5432/mdg_test
       APP_ENV: test
     run: php bin/console doctrine:migrations:migrate --no-interaction
   ```

4. Existing `phpunit` step picks up `DATABASE_URL` from env — no change needed.

**Tests to verify:**
- CI job green after a new migration is added
- CI job fails (as expected) if a migration contains a syntax error

**Status:** Open
