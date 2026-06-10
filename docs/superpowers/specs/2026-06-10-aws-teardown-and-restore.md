# AWS Teardown & Restoration Runbook

**Date:** 2026-06-10  
**Region:** eu-west-1  
**Account:** 730335358053

---

## Context

Full teardown of all AWS infrastructure to stop costs during development pause.
Terraform code, modules, and configuration files are **kept intact** — restore is a matter of running commands in order.

---

## Resources Being Destroyed

| Stack | Resources |
|---|---|
| `terraform/envs/dev` | VPC, RDS PostgreSQL (db.t3.micro), Bastion EC2, ECS clusters ×2, ECS services ×2, ECR repos ×2, Secrets Manager ×3, CloudWatch log groups, IAM roles/policies, App Autoscaling |
| `terraform/bootstrap` | S3 tfstate bucket (`newsletter-tfstate-730335358053`), DynamoDB lock table (`newsletter-tfstate-lock`), GitHub OIDC provider |
| SAM/CloudFormation | Lambda API (`newsletter-api-dev`), API Gateway, Cognito user pool (`eu-west-1_EU46ArwA7`) |

**Warning:** Cognito user pool deletion is permanent — all test users are lost. New restore creates a new pool with a different ID; update `terraform.tfvars` accordingly.

---

## Prerequisites (before any step)

- AWS CLI configured: `aws sts get-caller-identity` returns account `730335358053`
- Terraform ≥ 1.6 installed
- Working directory: `d:\Marco\apps\python-newsletter`

---

## TEARDOWN — Ordered Steps

### Step 1 — Destroy dev environment

```powershell
cd terraform\envs\dev
terraform destroy
```

Destroys all resources in `envs/dev`. S3 backend must still be alive at this point (destroyed later in step 3).

Expected duration: ~10–15 min (RDS instance deletion is the bottleneck).

### Step 2 — Empty the S3 tfstate bucket

S3 versioning is enabled — terraform cannot destroy a versioned bucket with objects in it. Empty it first.

```bash
# Delete all object versions
aws s3api delete-objects \
  --bucket newsletter-tfstate-730335358053 \
  --delete "$(aws s3api list-object-versions \
    --bucket newsletter-tfstate-730335358053 \
    --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' \
    --output json)" 2>/dev/null

# Delete all delete markers
aws s3api delete-objects \
  --bucket newsletter-tfstate-730335358053 \
  --delete "$(aws s3api list-object-versions \
    --bucket newsletter-tfstate-730335358053 \
    --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' \
    --output json)" 2>/dev/null
```

Verify empty: `aws s3 ls s3://newsletter-tfstate-730335358053/` → no output.

### Step 3 — Destroy bootstrap

```powershell
cd terraform\bootstrap
terraform destroy
```

Destroys S3 bucket, DynamoDB lock table, GitHub OIDC provider.  
Bootstrap state is local (`terraform\bootstrap\terraform.tfstate`) — delete it after destroy:

```powershell
Remove-Item terraform\bootstrap\terraform.tfstate
Remove-Item terraform\bootstrap\terraform.tfstate.backup -ErrorAction SilentlyContinue
```

### Step 4 — Delete SAM/CloudFormation stack

```bash
aws cloudformation delete-stack \
  --stack-name newsletter-api-dev \
  --region eu-west-1

# Wait for completion
aws cloudformation wait stack-delete-complete \
  --stack-name newsletter-api-dev \
  --region eu-west-1
```

---

## RESTORATION — Ordered Steps

### Prerequisites for restore

1. AWS credentials active for account `730335358053`
2. `terraform/envs/dev/terraform.tfvars` exists with correct values (see [terraform.tfvars.example](../../../terraform/envs/dev/terraform.tfvars.example))
3. New Cognito user pool IDs (if SAM stack re-deployed) — update `cognito_user_pool_id` and `cognito_client_id` in `terraform.tfvars`

### Step 1 — Bootstrap (creates S3 backend + GitHub OIDC)

```powershell
cd terraform\bootstrap
terraform init
terraform apply
```

Note the S3 bucket name from output — it matches account ID pattern `newsletter-tfstate-730335358053`.

### Step 2 — Init dev environment against new backend

The S3 backend config in `terraform/envs/dev/backend.tf` is hardcoded to the account ID bucket — no changes needed.

```powershell
cd terraform\envs\dev
terraform init
```

### Step 3 — Deploy dev environment

```powershell
terraform apply
```

Expected duration: ~15–20 min. Note the outputs:

| Output | Used for |
|---|---|
| `ecr_repo_url` | Push newsletter Docker image |
| `mdg_ecr_repo_url` | Push MDG Docker image |
| `cluster_endpoint` | DB connection |
| `bastion_instance_id` | SSM tunnel for DB access |

### Step 4 — Re-deploy SAM/CloudFormation stack (optional)

If Cognito + Lambda API needed:

```bash
cd infra
sam deploy --guided
```

Update `terraform/envs/dev/terraform.tfvars` with new Cognito user pool ID and client ID from SAM outputs, then re-run `terraform apply` in `envs/dev` to propagate to Fargate env vars.

### Step 5 — Push Docker images to ECR

```bash
# Authenticate
aws ecr get-login-password --region eu-west-1 \
  | docker login --username AWS --password-stdin <ecr_repo_url>

# Newsletter API
cd newsletter
docker build -t newsletter .
docker tag newsletter:latest <ecr_repo_url>:latest
docker push <ecr_repo_url>:latest

# MDG (PHP)
cd mdg
docker build -t mdg .
docker tag mdg:latest <mdg_ecr_repo_url>:latest
docker push <mdg_ecr_repo_url>:latest
```

### Step 6 — Scale ECS services up

```bash
# Newsletter
aws ecs update-service \
  --cluster newsletter-dev-cluster \
  --service newsletter-dev-newsletter-svc \
  --desired-count 1 \
  --region eu-west-1

# MDG
aws ecs update-service \
  --cluster newsletter-dev-mdg-cluster \
  --service newsletter-dev-mdg-svc \
  --desired-count 1 \
  --region eu-west-1
```

### Step 7 — Run DB migrations

Via SSM tunnel to bastion → Aurora (see `scripts/` for tunnel setup), then:

```bash
cd newsletter
alembic upgrade head
```

---

## Post-Restore Verification

Services run in private subnets with no ALB — verify via ECS task status and SSM tunnel.

```bash
# Check tasks running
aws ecs describe-services \
  --cluster newsletter-dev-cluster \
  --services newsletter-dev-newsletter-svc \
  --region eu-west-1 \
  --query 'services[0].{running:runningCount,desired:desiredCount,status:status}'

aws ecs describe-services \
  --cluster newsletter-dev-mdg-cluster \
  --services newsletter-dev-mdg-svc \
  --region eu-west-1 \
  --query 'services[0].{running:runningCount,desired:desiredCount,status:status}'
```

For full smoke test: open SSM tunnel to bastion → verify DB connectivity → run k6:
```bash
k6 run load_tests/newsletter/smoke.js
```

---

## Known Gotchas

| Issue | Fix |
|---|---|
| Cognito pool ID changes on restore | Update `cognito_user_pool_id` + `cognito_client_id` in `terraform.tfvars` before `terraform apply` |
| ECR repos empty after restore | Must push images before scaling services to desired_count > 0 |
| S3 destroy fails with `BucketNotEmpty` | Re-run Step 2 to empty versions/markers |
| RDS deletion takes 10+ min | Normal — wait for `terraform destroy` to complete |
| GitHub Actions CI fails after restore | OIDC role ARN may change — check bootstrap outputs and update repo secrets if needed |
