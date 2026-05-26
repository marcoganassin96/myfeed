# Troubleshooting: Newsletter Fargate 503 — Missing `env` Env Var

**Date:** 2026-05-25
**Environment:** `newsletter-dev` (Fargate)
**Status:** Resolved

---

## Symptom

After merging PR #13 (`feat/mds-fargate-deploy`) and running both Terraform and Fargate deploy workflows, 3 of 6 smoke tests returned 503:

```
GET /newsletters        → 503
POST /interactions      → 503
GET /subscriptions      → 503
GET /health             → 200  ✅
POST /deep-dive/{id}    → 200  ✅  (masked — see Root Cause #2)
MDG GET /health         → 200  ✅
```

---

## Infrastructure State

| Resource | Value |
|---|---|
| ECS Cluster | `newsletter-dev` |
| ECS Service | `newsletter-dev-newsletter-svc` |
| Task Def Family | `newsletter-dev-newsletter` |
| Failing revision | `:4` (no `env` env var) |
| Fixed revision | `:5` (with `env=dev`) |
| Config loaded on failure | `local.yaml` (`mdg.url = http://localhost:9000`) |
| Config loaded on success | `dev.yaml` (`mdg.url = http://internal-...elb.amazonaws.com`) |

---

## Root Cause Analysis

### Root Cause 1 — Missing `env` env var in task definition

`newsletter/src/settings.py` selects config file based on the `env` env var:
- `env=dev` → loads `config/dev.yaml` → correct internal MDG ALB URL
- `env` absent → loads `config/local.yaml` → `mdg.url = http://localhost:9000`

Task definition revision `:4` had no `env` env var. All handlers proxying to MDG (`/newsletters`, `/subscriptions`, `/interactions`) called `httpx` with `http://localhost:9000` → `ConnectError` → `_mdg.unavailable()` → 503.

### Root Cause 2 — `deep_dive.py` masked the failure

`POST /deep-dive/{id}` catches `httpx.ConnectError` and `httpx.TimeoutException` and returns a `StreamingResponse` with hardcoded fallback chunks → HTTP 200 even when MDG is unreachable. This made the smoke tests appear partially passing and hid the underlying connectivity failure.

### Root Cause 3 — Deploy pipeline never adopted new task definition revision

`ignore_changes = [desired_count, task_definition]` in `terraform/modules/fargate/main.tf` means Terraform manages task definition **revisions** but intentionally does NOT update the ECS service's task definition pointer. This is correct design (Terraform = infra, deploy pipeline = code). However, the deploy workflow in `.github/workflows/fargate-deploy.yml` called:

```bash
aws ecs update-service \
  --cluster ... \
  --service ... \
  --force-new-deployment
```

`--force-new-deployment` alone restarts the service using its **currently configured revision**. Without `--task-definition <latest-arn>`, the service never adopts a newer revision even if one exists. So even after `terraform apply` created revision `:5` with `env=dev`, the service kept running on revision `:4`.

### Why revision `:4` had no `env=dev`

GitHub Actions Terraform CI ran from a code version (master pre-merge or wrong branch state) that did not include the `env=dev` change. S3 Terraform state correctly reflected what CI applied — no corruption. Post-merge `terraform plan` locally detected the drift and `terraform apply` created revision `:5` with `env=dev`. State was consistent throughout; the root issue was CI applying an older code version.

---

## Fix

### Immediate — restore `env=dev` in task definition

Ran `terraform apply` locally from `terraform/envs/dev` (from master post-merge). Plan correctly detected missing `env=dev` and created new revision `:5` with the env var.

### Permanent — fix deploy workflow to use latest task definition revision

`fix/mds-fargate-deploy` branch: both `fargate-deploy.yml` and `mdg-fargate-deploy.yml` updated to derive the task definition family from the service name, fetch the latest revision ARN, and pass it explicitly to `update-service`:

```yaml
- name: Force ECS redeployment
  run: |
    TASK_DEF_FAMILY="${{ vars.ECS_SERVICE }}"
    TASK_DEF_FAMILY="${TASK_DEF_FAMILY%-svc}"
    LATEST_TASK_DEF=$(aws ecs describe-task-definition \
      --task-definition "$TASK_DEF_FAMILY" \
      --query 'taskDefinition.taskDefinitionArn' \
      --output text \
      --region eu-west-1)
    aws ecs update-service \
      --cluster "${{ vars.ECS_CLUSTER }}" \
      --service "${{ vars.ECS_SERVICE }}" \
      --task-definition "$LATEST_TASK_DEF" \
      --desired-count 1 \
      --force-new-deployment \
      --region eu-west-1 \
      --output json > /dev/null
```

---

## Verification

After merging `fix/mds-fargate-deploy` and re-running the deploy workflow from master, all 6 smoke tests must pass.

---

## Lessons Learned

### 1. `ignore_changes = [task_definition]` is intentional — and requires the deploy pipeline to do its job

Terraform's `ignore_changes = [task_definition]` on the ECS service is correct design: it prevents Terraform infra changes from accidentally rolling back a deployment. The pattern assumes the deploy pipeline will explicitly fetch and pass the latest task definition revision on every deploy. When the pipeline does not do this, Terraform changes (new env vars, CPU, memory) are silently ignored by the service forever.

**Rule:** Any Terraform change to a task definition only takes effect on the next deploy IF the workflow passes `--task-definition <latest-arn>`.

### 2. `--force-new-deployment` alone is not enough

`aws ecs update-service --force-new-deployment` = "restart the service with whatever revision it currently uses." It does NOT mean "use the latest revision." Always pair it with `--task-definition` to make the service adopt a new revision.

### 3. Creating a new task definition revision does not update the running service

Terraform `apply` can create revision `:5` without ever touching the service. The service keeps running revision `:4` until explicitly told otherwise. "New revision exists" ≠ "service uses it."

### 4. Missing `env` var fails silently — wrong config loads with no error

`settings.py` falls back to `local.yaml` when `env` is absent. No exception, no warning in logs, just wrong config. All symptoms (503s on MDG-proxied endpoints) appeared to be network failures — the real cause was `mdg.url = localhost:9000`. Always verify env var presence in ECS task via Console or `describe-task-definition` when debugging connectivity issues.

### 5. Watch for fallback behavior masking failures

`deep_dive.py` catches `ConnectError` and returns a 200 with hardcoded content instead of propagating the error. Smoke tests showed `/deep-dive` as green while every other MDG-proxied endpoint was failing. When debugging 503s, check ALL endpoints including ones that appear healthy — they may be hiding the same root cause behind a fallback.

### 6. GitHub Actions Terraform CI must run from master post-merge

If CI Terraform runs from a branch that pre-dates an infrastructure change, the state reflects that older code. The fix merged to master, but if CI runs before merge (or from wrong ref), the newer revision won't be created. Always verify the Terraform CI workflow ran from the correct post-merge commit.
