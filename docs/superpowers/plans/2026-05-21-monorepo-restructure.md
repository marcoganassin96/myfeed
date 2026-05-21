# Monorepo Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the repo so each service module owns its files under a named top-level folder (`newsletter/` for Python FastAPI, `mdg/` for PHP Symfony), with shared infra (docker-compose, migrations, terraform, scripts/deploy, load_tests) at root.

**Architecture:** Move Python source, tests, config files, requirements, Dockerfile, and ops scripts into `newsletter/`. Move k6 scenarios into `load_tests/newsletter/`. Keep shell deploy scripts and shared infra at root. Six atomic commits on branch `feat/monorepo-restructure`, each leaving tests green.

**Tech Stack:** Python 3.12, FastAPI, pytest, k6, GitHub Actions, Bash

---

## File Map

### Created
- `newsletter/` — Python module root
- `newsletter/src/` — moved from `src/`
- `newsletter/tests/` — moved from `tests/`
- `newsletter/scripts/` — moved from `scripts/*.py`
- `newsletter/pytest.ini` — moved from `pytest.ini`
- `newsletter/pyrightconfig.json` — moved from `pyrightconfig.json`
- `newsletter/requirements.txt` — moved
- `newsletter/requirements-dev.txt` — moved
- `newsletter/requirements-fargate.txt` — moved
- `newsletter/Dockerfile` — moved
- `load_tests/newsletter/` — moved from `load_tests/*.js`

### Modified (content changes)
- `newsletter/scripts/paths.py` — fix `ROOT_DIR` depth (`parent.parent`)
- `newsletter/scripts/steps.py` — update `LOAD_TEST_DIR` to `load_tests/newsletter`
- `newsletter/scripts/run_load_tests.py` — update `LOAD_TESTS` path
- `.github/workflows/fargate-deploy.yml` — update pip/pytest/docker paths
- `scripts/deploy_fargate.sh` — update docker build context

### Kept at root (shared infra, no changes)
- `docker-compose.yml` — postgres + redis + mdg only (newsletter runs via uvicorn directly)
- `migrations/`
- `terraform/`
- `config/`
- `scripts/deploy.sh`, `scripts/deploy_fargate.sh`, `scripts/deploy_k6_runner.sh`
- `CLAUDE.md`

---

## Task 1: Create branch

**Files:** none

- [ ] **Step 1: Create and switch to feature branch**

```bash
git checkout -b feat/monorepo-restructure
```

Expected: `Switched to a new branch 'feat/monorepo-restructure'`

---

## Task 2: Move Python source into `newsletter/`

**Files:**
- Create: `newsletter/src/` (moved from `src/`)
- Create: `newsletter/tests/` (moved from `tests/`)
- Create: `newsletter/pytest.ini` (moved from `pytest.ini`)
- Create: `newsletter/pyrightconfig.json` (moved from `pyrightconfig.json`)
- Create: `newsletter/requirements.txt` (moved)
- Create: `newsletter/requirements-dev.txt` (moved)
- Create: `newsletter/requirements-fargate.txt` (moved)
- Create: `newsletter/Dockerfile` (moved)

- [ ] **Step 1: Move files with git mv (preserves history)**

```bash
mkdir newsletter
git mv src newsletter/src
git mv tests newsletter/tests
git mv pytest.ini newsletter/pytest.ini
git mv pyrightconfig.json newsletter/pyrightconfig.json
git mv requirements.txt newsletter/requirements.txt
git mv requirements-dev.txt newsletter/requirements-dev.txt
git mv requirements-fargate.txt newsletter/requirements-fargate.txt
git mv Dockerfile newsletter/Dockerfile
```

- [ ] **Step 2: Verify tests pass from new location**

```bash
cd newsletter && pytest tests/ -v
```

Expected: all tests green (pytest.ini and pyrightconfig.json paths are relative to their file location — no content change needed).

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor(monorepo): move Python source into newsletter/ module"
```

---

## Task 3: Move Python scripts into `newsletter/scripts/`

**Files:**
- Create: `newsletter/scripts/` (moved from `scripts/*.py`)
- Modify: `newsletter/scripts/paths.py` — line 6: `ROOT_DIR = SCRIPTS_DIR.parent.parent`
- Modify: `newsletter/scripts/steps.py` — line 3: `LOAD_TEST_DIR = "load_tests/newsletter"`
- Modify: `newsletter/scripts/run_load_tests.py` — line 42: `LOAD_TESTS = ROOT_DIR / "load_tests" / "newsletter"`

- [ ] **Step 1: Move Python scripts with git mv**

```bash
git mv scripts/00_seed.py newsletter/scripts/00_seed.py
git mv scripts/01_prewarm.py newsletter/scripts/01_prewarm.py
git mv scripts/02_create_test_tokens.py newsletter/scripts/02_create_test_tokens.py
git mv scripts/03_get_load_test_ids.py newsletter/scripts/03_get_load_test_ids.py
git mv scripts/config.py newsletter/scripts/config.py
git mv scripts/flush_redis.py newsletter/scripts/flush_redis.py
git mv scripts/models.py newsletter/scripts/models.py
git mv scripts/paths.py newsletter/scripts/paths.py
git mv scripts/pipeline.py newsletter/scripts/pipeline.py
git mv scripts/run_load_tests.py newsletter/scripts/run_load_tests.py
git mv scripts/scale_down.py newsletter/scripts/scale_down.py
git mv scripts/scale_up.py newsletter/scripts/scale_up.py
git mv scripts/steps.py newsletter/scripts/steps.py
git mv scripts/tunnel.py newsletter/scripts/tunnel.py
git mv scripts/utils.py newsletter/scripts/utils.py
```

- [ ] **Step 2: Fix ROOT_DIR depth in `newsletter/scripts/paths.py`**

Change line 6 from:
```python
ROOT_DIR     = SCRIPTS_DIR.parent
```
To:
```python
ROOT_DIR     = SCRIPTS_DIR.parent.parent
```

Full updated file:
```python
"""Central path constants for all scripts in this directory."""
import pathlib
from enum import StrEnum

SCRIPTS_DIR  = pathlib.Path(__file__).parent
ROOT_DIR     = SCRIPTS_DIR.parent.parent
OUT_DIR      = SCRIPTS_DIR / "out"
CONFIG_DIR   = ROOT_DIR / "config"
CONFIG_LOCAL = CONFIG_DIR / "local.yaml"
CONFIG_DEV   = CONFIG_DIR / "dev.yaml"

class OutFile(StrEnum):
    SEED_RESULT = "00_seed_result.json"
    TOKENS_TXT  = "02_tokens.txt"
    TOKENS_ENV  = "02_tokens.env"
    IDS_ENV     = "03_ids.env"

def get_out_filepath(env: str, file_name: OutFile) -> pathlib.Path:
    path = OUT_DIR / env / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

# --- script files (used by pipeline.py) ---
SEED_SCRIPT         = SCRIPTS_DIR / "00_seed.py"
PREWARM_SCRIPT      = SCRIPTS_DIR / "01_prewarm.py"
TOKENS_SCRIPT       = SCRIPTS_DIR / "02_create_test_tokens.py"
IDS_SCRIPT          = SCRIPTS_DIR / "03_get_load_test_ids.py"
LOAD_TESTS_SCRIPT   = SCRIPTS_DIR / "04_run_load_tests.py"
FLUSH_SCRIPT        = SCRIPTS_DIR / "flush_redis.py"
SCALE_UP_SCRIPT     = SCRIPTS_DIR / "scale_up.py"
SCALE_DOWN_SCRIPT   = SCRIPTS_DIR / "scale_down.py"
```

- [ ] **Step 3: Fix `LOAD_TEST_DIR` in `newsletter/scripts/steps.py`**

Change line 3 from:
```python
LOAD_TEST_DIR = "load_tests"
```
To:
```python
LOAD_TEST_DIR = "load_tests/newsletter"
```

- [ ] **Step 4: Fix `LOAD_TESTS` path in `newsletter/scripts/run_load_tests.py`**

Change line 42 from:
```python
LOAD_TESTS = ROOT_DIR / "load_tests"
```
To:
```python
LOAD_TESTS = ROOT_DIR / "load_tests" / "newsletter"
```

- [ ] **Step 5: Verify scripts import correctly**

```bash
cd newsletter && python -c "import sys; sys.path.insert(0, 'scripts'); from paths import ROOT_DIR, LOAD_TESTS_SCRIPT; print(ROOT_DIR); print(LOAD_TESTS_SCRIPT)"
```

Expected: ROOT_DIR prints repo root (not `newsletter/`), script paths print `newsletter/scripts/...`

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(monorepo): move Python scripts into newsletter/scripts/"
```

---

## Task 4: Restructure `load_tests/` into `load_tests/newsletter/`

**Files:**
- Create: `load_tests/newsletter/` (moved from `load_tests/*.js`)
- k6 relative imports (`./config.js`, `./summary.js`) work unchanged — all files move together

- [ ] **Step 1: Move all k6 files**

```bash
mkdir load_tests/newsletter
git mv load_tests/capacity_benchmark.js load_tests/newsletter/capacity_benchmark.js
git mv load_tests/cold_start_stress.js load_tests/newsletter/cold_start_stress.js
git mv load_tests/config.js load_tests/newsletter/config.js
git mv load_tests/deep_dive_sse.js load_tests/newsletter/deep_dive_sse.js
git mv load_tests/mixed_realistic.js load_tests/newsletter/mixed_realistic.js
git mv load_tests/newsletter_cached.js load_tests/newsletter/newsletter_cached.js
git mv load_tests/newsletter_uncached.js load_tests/newsletter/newsletter_uncached.js
git mv load_tests/smoke.js load_tests/newsletter/smoke.js
git mv load_tests/summary.js load_tests/newsletter/summary.js
```

- [ ] **Step 2: Verify k6 can parse a scenario (dry-run)**

```bash
k6 inspect load_tests/newsletter/smoke.js
```

Expected: prints scenario config with no import errors. Skip if k6 not installed locally.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor(monorepo): move k6 scenarios into load_tests/newsletter/"
```

---

## Task 5: Update CI workflow paths

**Files:**
- Modify: `.github/workflows/fargate-deploy.yml`

Three changes:
1. `pip install` — add `working-directory: newsletter`
2. `pytest` — add `working-directory: newsletter`
3. `docker build` — change context from `.` to `newsletter/`

- [ ] **Step 1: Update `.github/workflows/fargate-deploy.yml`**

Replace the `Install dependencies` step:
```yaml
      - name: Install dependencies
        run: pip install -r requirements-dev.txt
```
With:
```yaml
      - name: Install dependencies
        working-directory: newsletter
        run: pip install -r requirements-dev.txt
```

Replace the `Run tests` step:
```yaml
      - name: Run tests
        run: pytest tests/ -v --tb=short
```
With:
```yaml
      - name: Run tests
        working-directory: newsletter
        run: pytest tests/ -v --tb=short
```

Replace the `Build and push Docker image` step:
```yaml
      - name: Build and push Docker image
        run: |
          docker build -t "${{ vars.ECR_REPO_URL }}:latest" .
          docker push "${{ vars.ECR_REPO_URL }}:latest"
```
With:
```yaml
      - name: Build and push Docker image
        run: |
          docker build -t "${{ vars.ECR_REPO_URL }}:latest" newsletter/
          docker push "${{ vars.ECR_REPO_URL }}:latest"
```

- [ ] **Step 2: Verify YAML is valid**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/fargate-deploy.yml'))" && echo OK
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/fargate-deploy.yml
git commit -m "ci: update fargate-deploy paths for newsletter/ module"
```

---

## Task 6: Update deploy shell script

**Files:**
- Modify: `scripts/deploy_fargate.sh` — line 18

- [ ] **Step 1: Fix docker build context in `scripts/deploy_fargate.sh`**

Change line 18 from:
```bash
docker build -t newsletter:latest "$ROOT_DIR"
```
To:
```bash
docker build -t newsletter:latest "$ROOT_DIR/newsletter"
```

- [ ] **Step 2: Verify script syntax**

```bash
bash -n scripts/deploy_fargate.sh && echo OK
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scripts/deploy_fargate.sh
git commit -m "chore(scripts): update deploy_fargate.sh build context to newsletter/"
```

---

## Task 7: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` — File Structure section

- [ ] **Step 1: Update File Structure section in `CLAUDE.md`**

Replace the `## File Structure` code block with:

```
newsletter/
  src/
    main.py
    auth.py
    dependencies.py
    db_async.py
    cache_async.py
    fields.py
    response.py
    settings.py
    db.py
    cache.py
    handlers/
      newsletters.py
      subscriptions.py
      interactions.py
      deep_dive.py
  tests/
    conftest.py
    test_*.py
  scripts/
    00_seed.py
    01_prewarm.py
    02_create_test_tokens.py
    03_get_load_test_ids.py
    flush_redis.py
    pipeline.py
    run_load_tests.py
    scale_up.py / scale_down.py
    config.py / models.py / paths.py / steps.py / tunnel.py / utils.py
    out/
  pytest.ini
  pyrightconfig.json
  requirements.txt / requirements-dev.txt / requirements-fargate.txt
  Dockerfile
mdg/
  src/
  tests/
  composer.json
  phpunit.xml.dist
  Dockerfile
load_tests/
  newsletter/
    config.js
    smoke.js
    newsletter_cached.js / newsletter_uncached.js
    mixed_realistic.js / deep_dive_sse.js
    capacity_benchmark.js / cold_start_stress.js
    summary.js
  mdg/                   (future)
scripts/
  deploy.sh
  deploy_fargate.sh
  deploy_k6_runner.sh
migrations/
  001_initial_schema.sql
  002_deep_dives.sql
terraform/
  modules/fargate/
  envs/dev/
config/
  common.yaml / dev.yaml / local.yaml
docker-compose.yml
infra/
  template.yaml
```

Also update the **Validation** section commands:
```bash
# Unit tests
cd newsletter && pytest tests/ -v
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md file structure for monorepo layout"
```

---

## Final verification

- [ ] **Run full test suite from new location**

```bash
cd newsletter && pytest tests/ -v
```

Expected: all tests green, zero failures, zero skips.

- [ ] **Check no orphan references to old paths**

```bash
grep -r "\"src/" .github/ scripts/ --include="*.yml" --include="*.sh" | grep -v newsletter/
grep -r "requirements-dev.txt" .github/ --include="*.yml" | grep -v "working-directory\|newsletter/"
```

Expected: no matches (all references updated).
