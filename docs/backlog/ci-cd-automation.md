# CI/CD Automation

Automation gaps identified during Phase 1 development. Each item is a concrete action that would have caught or prevented a real incident.

---

## Background

During load-test preparation (2026-05-08), Lambda functions were deployed without bundled pip dependencies (`psycopg2`, `redis`). The error surfaced only after k6 ran 43K VU-iterations — all failing. A minimal post-deploy smoke test would have caught it in seconds.

Reference: [2026-05-08 incident](../troubleshooting/2026-05-08-lambda-missing-psycopg2-k6-all-checks-failed.md)

---

## Items

### 1. Post-deploy smoke test in `scripts/pipeline.py`

**What:** After `sam deploy`, run a single GET `/newsletters/{id}` and POST `/interactions` before starting k6. Fail fast if either returns non-200.

**Why:** Current pipeline jumps straight from deploy to load test. Any Lambda crash (import error, env var missing, VPC misconfiguration) generates thousands of failed VU-iterations before anyone notices.

**How to implement:**
- Add step `04_smoke.py` (or inline in `pipeline.py`) between deploy and `04_run_load_tests.py`
- Use one valid token from `scripts/out/{env}/02_tokens.txt` and one newsletter ID from `03_ids.env`
- Assert HTTP 200; exit non-zero on failure
- `scripts/pipeline.py` already runs steps sequentially — insert the smoke check there

**Status:** Open

---

### 2. `sam local invoke` unit check in CI

**What:** Run `sam local invoke NewslettersFunction` (with a fixture event) in a GitHub Actions job triggered on every push to `feat/**` and `master`.

**Why:** `sam local invoke` builds and runs the Lambda container locally. It catches `ImportModuleError`, missing handler paths, and SAM template misconfigurations before any AWS deploy. Runs without network access — no RDS or Redis needed (use env var mocks).

**How to implement:**
- Add `.github/workflows/ci.yml`
- Steps: checkout → setup Python 3.12 → `pip install aws-sam-cli` → `sam build --template infra/template.yaml` → `sam local invoke NewslettersFunction --event tests/fixtures/event_get_newsletter.json --env-vars tests/fixtures/local_env.json`
- `local_env.json` provides dummy `DB_HOST`, `REDIS_HOST`, etc. so the import succeeds even if DB calls fail
- Gate: job must pass before merge to `master`

**Status:** Open

---

### 3. Unit tests in CI

**What:** Run `pytest tests/ -v` in the same GitHub Actions workflow.

**Why:** Tests already exist and run locally. Without CI enforcement, it's easy to push a breaking commit.

**How to implement:**
- Add job to `.github/workflows/ci.yml` (parallel with or before `sam local invoke`)
- Steps: checkout → setup Python 3.12 → `pip install -r requirements.txt -r src/requirements.txt` → `pytest tests/ -v`
- Fail workflow on any test failure

**Status:** Open

---

### 4. `sam build` output validation

**What:** In CI or in `scripts/pipeline.py`, assert that `sam build` output includes `Running PythonPipBuilder:ResolveDependencies`. Absence means no deps were bundled.

**Why:** If `src/requirements.txt` is ever deleted or the `CodeUri` path changes, the build succeeds silently but produces an incomplete Lambda zip.

**How to implement:**
- Capture `sam build` stdout
- `grep -q "ResolveDependencies"` or equivalent; exit non-zero if missing
- Can be a one-liner wrapper around `sam build`

**Status:** Open

---

### 5. CloudWatch error check after deploy

**What:** After `sam deploy`, tail CloudWatch for 30s and fail if any `ERROR` or `ImportModuleError` lines appear.

**Why:** SAM deploy succeeds even when the Lambda crashes on first invocation. A post-deploy cold-start check surfaces runtime errors immediately.

**How to implement:**
- After `sam deploy`, invoke each Lambda once via `aws lambda invoke`
- Check CloudWatch: `aws logs tail /aws/lambda/{function-name} --since 1m | grep -i error`
- Fail pipeline if any errors found

**Status:** Open
