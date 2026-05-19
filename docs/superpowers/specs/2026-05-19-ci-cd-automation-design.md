# CI/CD Automation — Design Spec

**Date:** 2026-05-19
**Scope:** GitHub Actions workflows for Terraform infra management and Fargate application deployment. Manual `workflow_dispatch` triggers, OIDC authentication, no long-lived AWS credentials.

---

## 1. Architecture

Two independent workflows. No coupling between them — infra changes and app deploys run separately.

```
GitHub Actions
├── terraform.yml          # workflow_dispatch: plan | apply
│   └── job: terraform
│       ├── OIDC → AWS role
│       ├── terraform init
│       ├── terraform plan  (always)
│       └── terraform apply (if action == apply)
│
└── fargate-deploy.yml     # workflow_dispatch: always deploys latest
    ├── job: test           # no AWS, fails fast
    │   └── pytest tests/ -v
    └── job: deploy         # needs: test
        ├── OIDC → AWS role
        ├── ECR login + docker build + push
        ├── ecs update-service --force-new-deployment
        ├── ecs wait services-stable
        └── curl /health  (smoke test)
```

### OIDC Trust

Single IAM role in `terraform/bootstrap/`. Trust policy scoped to `repo:MarcoGanassin/python-newsletter:*`. No per-environment roles — both workflows assume the same role.

---

## 2. OIDC IAM Role (`terraform/bootstrap/github_oidc.tf`)

New file added to existing bootstrap module. Bootstrapped once per AWS account, independent of `terraform/envs/dev/`.

**Resources:**

| Resource | Purpose |
|---|---|
| `aws_iam_openid_connect_provider` | Trust `token.actions.githubusercontent.com` |
| `aws_iam_role.github_actions` | Assumable by `repo:MarcoGanassin/python-newsletter:*` |
| `aws_iam_role_policy.github_actions` | Inline policy — least-privilege for both workflows |

**Inline policy permissions:**

| Permission set | Workflow |
|---|---|
| `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`, `ecr:PutImage`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:BatchCheckLayerAvailability` | fargate-deploy |
| `ecs:UpdateService`, `ecs:DescribeServices`, `ecs:DescribeTaskDefinition` | fargate-deploy |
| `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, `s3:DeleteObject` on `newsletter-tfstate-*` | terraform |
| `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:DeleteItem` on `newsletter-tfstate-lock` | terraform |
| All actions on VPC, ECS, ECR, ALB, IAM, SG, CloudWatch resources managed by Terraform | terraform apply |
| `logs:DescribeLogGroups`, `logs:GetLogEvents` | terraform (optional post-apply check) |

**New bootstrap output:**
```hcl
output "github_actions_role_arn" {
  value = aws_iam_role.github_actions.arn
}
```

**Setup command (run once after bootstrap apply):**
```bash
terraform -chdir=terraform/bootstrap apply
terraform -chdir=terraform/bootstrap output -raw github_actions_role_arn
# → copy ARN into GitHub Actions Variable AWS_ROLE_ARN
```

---

## 3. GitHub Actions Variables

Set in repo **Settings → Secrets and variables → Actions → Variables** (not Secrets — values are non-sensitive resource identifiers).

| Variable | How to get value |
|---|---|
| `AWS_ROLE_ARN` | `terraform -chdir=terraform/bootstrap output -raw github_actions_role_arn` |
| `ECR_REPO_URL` | `terraform -chdir=terraform/envs/dev output -raw ecr_repo_url` |
| `ECS_CLUSTER` | `terraform -chdir=terraform/envs/dev output -raw ecs_cluster` |
| `ECS_SERVICE` | `terraform -chdir=terraform/envs/dev output -raw ecs_service` |
| `ALB_DNS` | `terraform -chdir=terraform/envs/dev output -raw alb_dns` |

AWS region hardcoded as `eu-west-1` in both workflows. Update these variables if Terraform outputs change.

---

## 4. Workflow: `terraform.yml`

**File:** `.github/workflows/terraform.yml`

**Inputs:**

| Input | Type | Default | Options |
|---|---|---|---|
| `action` | choice | `plan` | `plan`, `apply` |
| `env` | choice | `dev` | `dev` |

**Job: `terraform`**

```yaml
runs-on: ubuntu-latest
permissions:
  id-token: write
  contents: read

steps:
  - uses: actions/checkout@v4

  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: ${{ vars.AWS_ROLE_ARN }}
      aws-region: eu-west-1

  - uses: hashicorp/setup-terraform@v3
    with:
      terraform_version: "~> 1.x"   # pinned to match .terraform.lock.hcl

  - name: terraform init
    run: terraform init -backend-config=backend.hcl
    working-directory: terraform/envs/${{ inputs.env }}

  - name: terraform plan
    run: terraform plan -out=plan.tfplan
    working-directory: terraform/envs/${{ inputs.env }}

  - name: terraform apply
    if: inputs.action == 'apply'
    run: terraform apply plan.tfplan
    working-directory: terraform/envs/${{ inputs.env }}
```

No approval gate between plan and apply — `apply` is chosen deliberately at dispatch time.

---

## 5. Workflow: `fargate-deploy.yml`

**File:** `.github/workflows/fargate-deploy.yml`

**Inputs:** none — always deploys `latest` from the dispatched branch to `dev`.

**Job 1: `test`**

```yaml
runs-on: ubuntu-latest

steps:
  - uses: actions/checkout@v4

  - uses: actions/setup-python@v5
    with:
      python-version: "3.12"

  - name: install dependencies
    run: pip install -r requirements-fargate.txt -r requirements-dev.txt

  - name: pytest
    run: pytest tests/ -v --tb=short
```

**Job 2: `deploy`** (`needs: test`)

```yaml
runs-on: ubuntu-latest
permissions:
  id-token: write
  contents: read

steps:
  - uses: actions/checkout@v4

  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: ${{ vars.AWS_ROLE_ARN }}
      aws-region: eu-west-1

  - name: ECR login
    run: |
      aws ecr get-login-password --region eu-west-1 \
        | docker login --username AWS --password-stdin \
          $(echo ${{ vars.ECR_REPO_URL }} | cut -d/ -f1)

  - name: docker build + push
    run: |
      docker build -t ${{ vars.ECR_REPO_URL }}:latest .
      docker push ${{ vars.ECR_REPO_URL }}:latest

  - name: ECS force redeployment
    run: |
      aws ecs update-service \
        --cluster ${{ vars.ECS_CLUSTER }} \
        --service ${{ vars.ECS_SERVICE }} \
        --force-new-deployment \
        --region eu-west-1 \
        --output json > /dev/null

  - name: wait for service stable
    run: |
      aws ecs wait services-stable \
        --cluster ${{ vars.ECS_CLUSTER }} \
        --services ${{ vars.ECS_SERVICE }} \
        --region eu-west-1
    timeout-minutes: 10

  - name: smoke test
    run: |
      curl -f --retry 3 --retry-delay 5 \
        http://${{ vars.ALB_DNS }}/health
```

The smoke test hits `/health` (no auth, per SAM template). Catches import errors and VPC misconfigs before k6 runs. Matches backlog item 1 intent.

---

## 6. File Changes Summary

| File | Action |
|---|---|
| `terraform/bootstrap/github_oidc.tf` | New — OIDC provider + IAM role + policy |
| `terraform/bootstrap/outputs.tf` | Add `github_actions_role_arn` output |
| `.github/workflows/terraform.yml` | New — Terraform plan/apply workflow |
| `.github/workflows/fargate-deploy.yml` | New — pytest + Docker build + ECS deploy |

No changes to existing `scripts/`, `infra/template.yaml`, or `terraform/envs/dev/`.

---

## 7. Deployment Sequence (first-time setup)

```bash
# 1. Add github_oidc.tf to bootstrap, re-apply
terraform -chdir=terraform/bootstrap apply

# 2. Set GitHub Actions Variables
terraform -chdir=terraform/bootstrap output -raw github_actions_role_arn   # → AWS_ROLE_ARN
terraform -chdir=terraform/envs/dev output -raw ecr_repo_url     # → ECR_REPO_URL
terraform -chdir=terraform/envs/dev output -raw ecs_cluster       # → ECS_CLUSTER
terraform -chdir=terraform/envs/dev output -raw ecs_service       # → ECS_SERVICE
terraform -chdir=terraform/envs/dev output -raw alb_dns           # → ALB_DNS

# 3. Push branch, go to GitHub Actions → run fargate-deploy workflow
# 4. For infra changes: run terraform workflow with action=plan, then action=apply
```

---

## 8. Out of Scope

- Automatic triggers on push/PR (manual dispatch only)
- `prod` environment (env input is extensible — add `terraform/envs/prod/` and add `prod` to the choice list)
- Docker image tagging beyond `latest` (no versioned rollback)
- SAM/Lambda deploy workflow (Lambda infra kept for reference, not actively deployed)
- Slack/email notifications on workflow completion
- Terraform plan output posted as PR comment
