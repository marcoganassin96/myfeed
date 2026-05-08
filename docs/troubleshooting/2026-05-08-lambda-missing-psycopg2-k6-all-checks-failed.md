# Troubleshooting: Lambda Missing psycopg2 — k6 100% Check Failure

**Date:** 2026-05-08
**Environment:** `newsletter-api-dev`, region `eu-west-1`
**Status:** Resolved

---

## Symptom

k6 `newsletter_cached` scenario (10s smoke run, 500 VUs) reported 100% check failure:

```
checks_succeeded...: 0.00%   0 out of 43334
✗ 200         ↳  0% — ✓ 0 / ✗ 21667
✗ has newsletter_id  ↳  0% — ✓ 0 / ✗ 21667
```

All requests returned `{"message": "Internal server error"}`.

---

## Discovery

### Step 1 — Manual curl smoke test

Instead of assuming a k6 configuration problem, a single curl confirmed the API itself was broken:

```bash
curl -X GET "$API_URL/newsletters/$NL_ID" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json"
# {"message": "Internal server error"}
```

HTTP 500 from API Gateway means Lambda crashed before returning a response.

### Step 2 — CloudWatch logs

```bash
aws logs tail /aws/lambda/newsletter-api-dev-NewslettersFunction-EoxoyyPPeveC \
  --since 9m --region eu-west-1
```

Error:

```
[ERROR] Runtime.ImportModuleError: Unable to import module 'handlers/newsletters':
No module named 'psycopg2'
```

---

## Root Cause

Two compounding issues — both required fixing before the Lambda could start.

### Issue 1 — No `requirements.txt` in `CodeUri` directory

`infra/template.yaml` sets `CodeUri: ../src` for all functions. SAM's Python builder installs pip dependencies from a `requirements.txt` file found inside the `CodeUri` directory. The project's `requirements.txt` lived at the repo root — not inside `src/` — so SAM found no dependencies to install, and `.aws-sam/build/` contained only source code.

```
repo root/
  requirements.txt        ← SAM never reads this
  src/
    db.py
    cache.py
    handlers/
    ...                   ← CodeUri points here; no requirements.txt → no deps bundled
```

### Issue 2 — `sam deploy` not using built artifacts

After adding `src/requirements.txt`, `sam build` ran correctly (`Running PythonPipBuilder:ResolveDependencies`) and produced an 8.5 MB build artifact in `.aws-sam/build/NewslettersFunction/` including psycopg2. However, the Lambda was still failing.

**Why:** `sam deploy` without `--template-file` was falling back to the source template (`infra/template.yaml`) instead of the built template (`.aws-sam/build/template.yaml`). The source template has `CodeUri: ../src`, so `sam deploy` packaged the raw `src/` directory — no installed deps — producing a 21 KB zip identical to the pre-fix deploys.

---

## What Would Have Caught This Sooner

| Precaution | How it helps |
|---|---|
| **Smoke-test the API before running k6** | One curl after deploy would have surfaced the 500 immediately, before spinning up hundreds of VUs |
| **Check CloudWatch after every deploy** | A quick `aws logs tail` after `sam deploy` catches import errors before any test is run |
| **`sam build` output review** | `sam build` prints `Running PythonPipBuilder:ResolveDependencies` when it installs deps. Absence of this line means no deps were bundled — easy to spot if you read the build output |
| **Add a deploy smoke-test step to the pipeline** | `scripts/pipeline.py` could call `04_smoke.py` (single GET + POST) immediately after deploy, failing fast before load tests run |
| **Lambda cold-start check in CI** | A `sam local invoke` test in CI (even with mocked env vars) would have caught the `ImportModuleError` before any AWS deploy |

---

## Fix

1. Add `src/requirements.txt` containing only Lambda runtime dependencies:

```
psycopg2-binary==2.9.9
redis==5.0.4
```

2. Update `scripts/deploy.sh` to:
   - Run `sam build --template-file infra/template.yaml` before deploy
   - Pass `--template-file .aws-sam/build/template.yaml` to `sam deploy` so it packages from the built artifacts, not the source tree

3. Redeploy:

```bash
./scripts/deploy.sh dev
```

3. Verify with curl before running k6:

```bash
TOKEN=$(head -n 1 scripts/out/dev/02_tokens.txt | xargs)
NL_ID=$(grep "NEWSLETTER_IDS" scripts/out/dev/03_ids.env | sed 's/.*=//' | cut -d',' -f1)
API_URL="https://4ete4i2b46.execute-api.eu-west-1.amazonaws.com/dev"
curl -X GET "$API_URL/newsletters/$NL_ID" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json"
# Expect: HTTP 200 + JSON body with newsletter_id
```

---

## Next Steps

- [x] Verify fix: curl returns 200 after redeploy
- [ ] Re-run `newsletter_cached` scenario (10s smoke first, then full 60s)
- [ ] Run remaining k6 scenarios: `newsletter_cold`, `deep_dive_sse`, `mixed_realistic`, `cold_start_stress`
- [ ] Add deploy smoke-test to `scripts/pipeline.py` so this class of error is caught automatically in future
