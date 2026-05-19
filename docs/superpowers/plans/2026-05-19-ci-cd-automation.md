# CI/CD Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two manual GitHub Actions workflows — one for Terraform plan/apply, one for pytest-gated Fargate deploy — authenticated via OIDC (no stored AWS keys).

**Architecture:** OIDC IAM role provisioned in `terraform/bootstrap/` (once per AWS account). Two independent `workflow_dispatch` workflows consume the role ARN from a GitHub Actions Variable. The Fargate deploy workflow runs pytest before building and pushing the Docker image, then waits for ECS service stability and smoke-tests `/health`.

**Tech Stack:** GitHub Actions, AWS OIDC, Terraform (AWS provider ~> 5.0), Docker, Amazon ECR, Amazon ECS Fargate, pytest.

**Working directory for all steps:** `.worktrees/feat/ci-cd-automation`

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `terraform/bootstrap/github_oidc.tf` | Create | OIDC provider + IAM role + inline policy |
| `terraform/bootstrap/outputs.tf` | Modify | Add `github_actions_role_arn` output |
| `.github/workflows/terraform.yml` | Create | Terraform plan/apply workflow |
| `.github/workflows/fargate-deploy.yml` | Create | pytest → docker build → ECS deploy workflow |

---

## Task 1: OIDC IAM Role in Bootstrap

**Files:**
- Create: `terraform/bootstrap/github_oidc.tf`
- Modify: `terraform/bootstrap/outputs.tf`

- [ ] **Step 1: Create `terraform/bootstrap/github_oidc.tf`**

```hcl
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

resource "aws_iam_role" "github_actions" {
  name = "newsletter-github-actions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:MarcoGanassin/python-newsletter:*"
        }
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "github_actions" {
  name = "newsletter-github-actions-policy"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "TerraformState"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:DeleteObject",
        ]
        Resource = [
          "arn:aws:s3:::newsletter-tfstate-*",
          "arn:aws:s3:::newsletter-tfstate-*/*",
        ]
      },
      {
        Sid    = "TerraformLock"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem",
        ]
        Resource = "arn:aws:dynamodb:eu-west-1:*:table/newsletter-tfstate-lock"
      },
      {
        Sid    = "AWSResourceManagement"
        Effect = "Allow"
        Action = [
          "ec2:*",
          "elasticache:*",
          "rds:*",
          "iam:*",
          "logs:*",
          "ecs:*",
          "ecr:*",
          "elasticloadbalancing:*",
          "application-autoscaling:*",
          "secretsmanager:*",
          "cognito-idp:*",
          "lambda:*",
          "apigateway:*",
          "cloudformation:*",
          "s3:*",
          "dynamodb:*",
          "ssm:*",
        ]
        Resource = "*"
      },
    ]
  })
}
```

- [ ] **Step 2: Add output to `terraform/bootstrap/outputs.tf`**

Append to the existing file (keep the three existing outputs, add this):

```hcl
output "github_actions_role_arn" {
  value = aws_iam_role.github_actions.arn
}
```

Full file after edit:

```hcl
output "state_bucket" {
  value = aws_s3_bucket.tfstate.bucket
}

output "lock_table" {
  value = aws_dynamodb_table.tfstate_lock.name
}

output "account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "github_actions_role_arn" {
  value = aws_iam_role.github_actions.arn
}
```

- [ ] **Step 3: Validate Terraform syntax**

```bash
terraform -chdir=terraform/bootstrap validate
```

Expected output:
```
Success! The configuration is valid.
```

If you see `Error: ...` fix the HCL before continuing.

- [ ] **Step 4: Plan — verify 3 new resources**

```bash
terraform -chdir=terraform/bootstrap plan
```

Expected: plan shows `3 to add` — `aws_iam_openid_connect_provider.github`, `aws_iam_role.github_actions`, `aws_iam_role_policy.github_actions`. Existing S3/DynamoDB resources show `0 changes`.

- [ ] **Step 5: Apply**

```bash
terraform -chdir=terraform/bootstrap apply
```

Type `yes` when prompted. Expected: `Apply complete! Resources: 3 added, 0 changed, 0 destroyed.`

- [ ] **Step 6: Capture role ARN**

```bash
terraform -chdir=terraform/bootstrap output -raw github_actions_role_arn
```

Expected output: `arn:aws:iam::730335358053:role/newsletter-github-actions`

Copy this value — needed in Task 2.

- [ ] **Step 7: Commit**

```bash
git add terraform/bootstrap/github_oidc.tf terraform/bootstrap/outputs.tf
git commit -m "infra(bootstrap): add GitHub Actions OIDC role"
```

---

## Task 2: Set GitHub Actions Variables

This task has no code — it's manual configuration in the GitHub UI. All values come from Terraform outputs.

- [ ] **Step 1: Gather all values**

Run these commands and save the outputs:

```bash
# Role ARN (from Task 1 — already have this)
terraform -chdir=terraform/bootstrap output -raw github_actions_role_arn

# ECR repo URL
terraform -chdir=terraform/envs/dev output -raw ecr_repo_url

# ECS cluster name
terraform -chdir=terraform/envs/dev output -raw ecs_cluster

# ECS service name
terraform -chdir=terraform/envs/dev output -raw ecs_service

# ALB DNS name
terraform -chdir=terraform/envs/dev output -raw alb_dns
```

- [ ] **Step 2: Set variables in GitHub**

Go to: `https://github.com/MarcoGanassin/python-newsletter/settings/variables/actions`

Click **New repository variable** for each:

| Name | Value |
|---|---|
| `AWS_ROLE_ARN` | ARN from `github_actions_role_arn` output |
| `ECR_REPO_URL` | URL from `ecr_repo_url` output |
| `ECS_CLUSTER` | Name from `ecs_cluster` output |
| `ECS_SERVICE` | Name from `ecs_service` output |
| `ALB_DNS` | DNS name from `alb_dns` output |

**Important:** Use the **Variables** tab, not the **Secrets** tab. These are non-sensitive resource identifiers.

---

## Task 3: Terraform Workflow

**Files:**
- Create: `.github/workflows/terraform.yml`

- [ ] **Step 1: Create `.github/workflows/` directory and write `terraform.yml`**

```yaml
name: Terraform

on:
  workflow_dispatch:
    inputs:
      action:
        description: "Terraform action"
        type: choice
        options:
          - plan
          - apply
        default: plan
      env:
        description: "Target environment"
        type: choice
        options:
          - dev
        default: dev

jobs:
  terraform:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.AWS_ROLE_ARN }}
          aws-region: eu-west-1

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "~> 1.9"

      - name: Terraform init
        working-directory: terraform/envs/${{ inputs.env }}
        run: terraform init

      - name: Terraform plan
        working-directory: terraform/envs/${{ inputs.env }}
        run: terraform plan -out=plan.tfplan

      - name: Terraform apply
        if: inputs.action == 'apply'
        working-directory: terraform/envs/${{ inputs.env }}
        run: terraform apply plan.tfplan
```

- [ ] **Step 2: Commit and push**

```bash
git add .github/workflows/terraform.yml
git commit -m "ci: add Terraform plan/apply workflow"
git push -u origin feat/ci-cd-automation
```

- [ ] **Step 3: Verify workflow appears in GitHub Actions**

Go to: `https://github.com/MarcoGanassin/python-newsletter/actions`

Confirm `Terraform` workflow is listed. Click **Run workflow** — select `action: plan`, `env: dev`. Run it.

Expected: workflow completes green, plan output is visible in the logs showing current infra state (0 to add/change/destroy if infra is up to date).

---

## Task 4: Fargate Deploy Workflow

**Files:**
- Create: `.github/workflows/fargate-deploy.yml`

- [ ] **Step 1: Write `.github/workflows/fargate-deploy.yml`**

```yaml
name: Fargate Deploy

on:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r requirements-dev.txt

      - name: Run tests
        run: pytest tests/ -v --tb=short

  deploy:
    needs: test
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.AWS_ROLE_ARN }}
          aws-region: eu-west-1

      - name: ECR login
        run: |
          aws ecr get-login-password --region eu-west-1 \
            | docker login --username AWS --password-stdin \
                "$(echo "${{ vars.ECR_REPO_URL }}" | cut -d/ -f1)"

      - name: Build and push Docker image
        run: |
          docker build -t "${{ vars.ECR_REPO_URL }}:latest" .
          docker push "${{ vars.ECR_REPO_URL }}:latest"

      - name: Force ECS redeployment
        run: |
          aws ecs update-service \
            --cluster "${{ vars.ECS_CLUSTER }}" \
            --service "${{ vars.ECS_SERVICE }}" \
            --force-new-deployment \
            --region eu-west-1 \
            --output json > /dev/null

      - name: Wait for service stable
        timeout-minutes: 10
        run: |
          aws ecs wait services-stable \
            --cluster "${{ vars.ECS_CLUSTER }}" \
            --services "${{ vars.ECS_SERVICE }}" \
            --region eu-west-1

      - name: Smoke test
        run: |
          curl -f --retry 3 --retry-delay 5 \
            "http://${{ vars.ALB_DNS }}/health"
```

- [ ] **Step 2: Commit and push**

```bash
git add .github/workflows/fargate-deploy.yml
git commit -m "ci: add pytest-gated Fargate deploy workflow"
git push
```

- [ ] **Step 3: Verify workflow appears in GitHub Actions**

Go to: `https://github.com/MarcoGanassin/python-newsletter/actions`

Confirm `Fargate Deploy` workflow is listed. Click **Run workflow**.

Expected progression:
1. `test` job runs — 49 tests pass
2. `deploy` job starts (only after `test` passes)
3. ECR login → docker build → push → ECS force-redeploy → `services-stable` wait (~60–120s) → smoke test hits `/health` → 200 OK
4. Workflow completes green

If `test` fails, `deploy` job is skipped automatically (shown as grey/skipped in GitHub UI).

---

## Self-Review

**Spec coverage:**
- Section 1 (OIDC IAM role) → Task 1 ✓
- Section 2 (GitHub Variables) → Task 2 ✓
- Section 3 (terraform.yml) → Task 3 ✓
- Section 4 (fargate-deploy.yml with test gate + smoke) → Task 4 ✓

**Placeholder scan:** No TBDs. All steps have complete code. ✓

**Type/name consistency:**
- `ecs_cluster` / `ecs_service` output names verified against `terraform/envs/dev/outputs.tf` ✓
- `backend.tf` uses inline backend (no `-backend-config` flag needed) ✓
- `requirements-dev.txt` now includes `-r requirements-fargate.txt` (fastapi, httpx) ✓
