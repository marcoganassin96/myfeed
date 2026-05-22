# MDG Fargate Deployment Design

**Date:** 2026-05-21  
**Branch:** feature to be created  
**Status:** Approved

---

## Context

The MDG (Master Data Gateway) PHP Symfony service is implemented and merged (PR #10). It runs on port 9000, uses Doctrine ORM (`DATABASE_URL`) and Predis (`REDIS_URL`), and exposes a `/health` endpoint.

Newsletter FastAPI calls MDG over an internal ALB inside the VPC. The MDG has no public exposure.

Related specs:
- `docs/superpowers/specs/2026-05-20-mdg-symfony-design.md` — PHP implementation
- `docs/superpowers/specs/2026-05-13-fargate-serving-layer-design.md` — newsletter Fargate

Infrastructure is currently **free-tier** (RDS PostgreSQL `db.t3.micro`, no RDS Proxy). Premium upgrade path (Aurora Serverless v2 + RDS Proxy) is tracked in `docs/superpowers/plans/2026-04-28-restore-premium-infra.md`.

---

## Topology

```
Internet → Public ALB (port 80) → FastAPI ECS Fargate (port 8000)
                                        ↓ X-User-Id header (VPC-only trust)
                              Internal ALB (port 80, private subnets)
                                        ↓
                              MDG ECS Fargate (port 9000, private subnets)
                                  ↓               ↓
                          Aurora PostgreSQL    ElastiCache Redis
```

VPC isolation is the sole auth boundary between FastAPI and MDG (ADR-005).

---

## Architecture Decision

**New module `terraform/modules/fargate-mdg/`** — mirrors existing `fargate/` module, isolated from newsletter infrastructure. Zero risk of drift to already-deployed newsletter resources.

Rejected:
- Extend existing `fargate` module — touches deployed resources, high drift risk
- Inline resources in `envs/dev/main.tf` — not reusable across environments

---

## Terraform Module: `terraform/modules/fargate-mdg/`

### Files

| File | Responsibility |
|---|---|
| `main.tf` | All resources: ECR, ECS cluster, CloudWatch, IAM, secrets, SGs, internal ALB, task def, service, auto-scaling |
| `variables.tf` | Input variables |
| `outputs.tf` | `mdg_alb_dns_name`, `mdg_ecr_repo_url`, `mdg_cluster_name`, `mdg_service_name`, `mdg_fargate_sg_id`, `mdg_internal_alb_sg_id` |

### Resources in `main.tf`

```
aws_ecr_repository.main              — ECR repo "newsletter-mdg-dev"
aws_ecs_cluster.main                 — ECS cluster for MDG
aws_cloudwatch_log_group.main        — /ecs/newsletter-mdg-dev (7-day retention)
aws_iam_role.execution               — ECS task execution role
aws_iam_role_policy_attachment.execution  — AmazonECSTaskExecutionRolePolicy
aws_iam_role_policy.execution_secrets    — GetSecretValue on db_url + app_secret ARNs
random_password.app_secret           — 32-char alphanumeric APP_SECRET
aws_secretsmanager_secret.app_secret + _version  — stores APP_SECRET value
aws_secretsmanager_secret.db_url + _version      — stores full DATABASE_URL (composed)
aws_security_group.internal_alb      — ingress 80 from newsletter fargate SG
aws_security_group.mdg_fargate       — ingress 9000 from internal ALB SG
aws_security_group_rule.mdg_egress_https   — egress 443 to 0.0.0.0/0
aws_security_group_rule.mdg_egress_aurora  — egress 5432 to aurora SG
aws_security_group_rule.mdg_egress_redis   — egress 6379 to redis SG
aws_security_group_rule.aurora_ingress_mdg — ingress 5432 from MDG fargate SG (added to aurora SG)
aws_security_group_rule.redis_ingress_mdg  — ingress 6379 from MDG fargate SG (added to redis SG)
aws_lb.main                          — internal ALB, internal=true, private subnets
aws_lb_target_group.main             — port 9000, health_check path=/health
aws_lb_listener.main                 — port 80 → target group
aws_ecs_task_definition.main         — 512 CPU / 1024 MB, port 9000
aws_ecs_service.main                 — desired_count=0, FARGATE, private subnets
aws_appautoscaling_target.main       — min=0 max=2
aws_appautoscaling_policy.cpu        — CPU 70%, scale_out_cooldown=60
```

### DATABASE_URL secret (free-tier)

```hcl
resource "aws_secretsmanager_secret_version" "db_url" {
  secret_id     = aws_secretsmanager_secret.db_url.id
  secret_string = format("postgresql://%s:%s@%s/%s?serverVersion=15&charset=utf8",
    var.db_user, var.db_password, var.db_host, var.db_name
  )
}
```

**Premium upgrade path:** change `db_host` input in `envs/dev/main.tf` from `module.aurora.cluster_endpoint` to `module.aurora.rds_proxy_endpoint`. No module code change.

### Container env vars

| Name | Type | Source |
|---|---|---|
| `DATABASE_URL` | secret | `aws_secretsmanager_secret.db_url.arn` |
| `APP_SECRET` | secret | `aws_secretsmanager_secret.app_secret.arn` |
| `APP_ENV` | plain | `"prod"` |
| `REDIS_URL` | plain | `redis://${var.redis_endpoint}` |

### variables.tf inputs

```
name_prefix            string   (default "newsletter-mdg")
vpc_id                 string
private_subnet_ids     list(string)
aurora_sg_id           string   — aurora SG; module adds ingress rule
redis_sg_id            string   — redis SG; module adds ingress rule
newsletter_fargate_sg_id  string  — newsletter fargate SG; internal ALB allows ingress from it
db_host                string   — module.aurora.cluster_endpoint (free tier)
db_name                string   (default "newsletter")
db_user                string   (default "newsletter")
db_password            string   sensitive — module.aurora.db_password
redis_endpoint         string   — module.redis.redis_endpoint
region                 string   (default "eu-west-1")
image_tag              string   (default "latest")
```

---

## Changes to Existing Files

### `terraform/modules/fargate/outputs.tf`

Add one output (needed by `fargate-mdg` module to set internal ALB ingress rule):

```hcl
output "fargate_sg_id" {
  value = aws_security_group.fargate.id
}
```

### `terraform/envs/dev/main.tf`

Add module block + cross-module SG rule:

```hcl
module "fargate_mdg" {
  source                   = "../../modules/fargate-mdg"
  name_prefix              = "${var.name_prefix}-mdg"
  vpc_id                   = module.vpc.vpc_id
  private_subnet_ids       = module.vpc.private_subnet_ids
  aurora_sg_id             = module.vpc.aurora_sg_id
  redis_sg_id              = module.vpc.redis_sg_id
  newsletter_fargate_sg_id = module.fargate.fargate_sg_id
  db_host                  = module.aurora.cluster_endpoint
  db_name                  = var.db_name
  db_user                  = var.db_user
  db_password              = module.aurora.db_password
  redis_endpoint           = module.redis.redis_endpoint
  region                   = var.region
}

# Newsletter Fargate → Internal ALB (port 80)
resource "aws_security_group_rule" "newsletter_egress_mdg_alb" {
  type                     = "egress"
  from_port                = 80
  to_port                  = 80
  protocol                 = "tcp"
  security_group_id        = module.fargate.fargate_sg_id
  source_security_group_id = module.fargate_mdg.mdg_internal_alb_sg_id
}
```

### `terraform/envs/dev/outputs.tf`

Add MDG outputs:

```hcl
output "mdg_alb_dns" {
  value = module.fargate_mdg.mdg_alb_dns_name
}

output "mdg_ecr_repo_url" {
  value = module.fargate_mdg.mdg_ecr_repo_url
}

output "mdg_ecs_cluster" {
  value = module.fargate_mdg.mdg_cluster_name
}

output "mdg_ecs_service" {
  value = module.fargate_mdg.mdg_service_name
}
```

### `config/dev.yaml`

After `terraform apply`, replace placeholder with real internal ALB DNS:

```yaml
mdg:
  url: "http://<mdg_alb_dns output value>"
```

Then redeploy newsletter so it picks up the real URL.

---

## Security Groups Summary

| Rule | From → To | Port |
|---|---|---|
| internal-alb-sg ingress | newsletter-fargate-sg → internal-alb-sg | 80 |
| newsletter-fargate-sg egress | newsletter-fargate-sg → internal-alb-sg | 80 |
| mdg-fargate-sg ingress | internal-alb-sg → mdg-fargate-sg | 9000 |
| mdg-fargate-sg egress HTTPS | mdg-fargate-sg → 0.0.0.0/0 | 443 |
| mdg-fargate-sg egress Aurora | mdg-fargate-sg → aurora-sg | 5432 |
| mdg-fargate-sg egress Redis | mdg-fargate-sg → redis-sg | 6379 |
| aurora-sg ingress MDG | mdg-fargate-sg → aurora-sg | 5432 |
| redis-sg ingress MDG | mdg-fargate-sg → redis-sg | 6379 |

---

## CI/CD

### New workflow: `.github/workflows/mdg-fargate-deploy.yml`

Mirrors `fargate-deploy.yml`. Jobs:

1. **test** — PHPUnit (PHP 8.4, Composer install, `phpunit`)
2. **deploy** (needs test):
   - Configure AWS credentials (OIDC: `vars.AWS_ROLE_ARN`)
   - ECR login
   - `docker build -f mdg/Dockerfile -t "${{ vars.MDG_ECR_REPO_URL }}:latest" ./mdg`
   - `docker push "${{ vars.MDG_ECR_REPO_URL }}:latest"`
   - `aws ecs update-service --desired-count 1 --force-new-deployment`
   - `aws ecs wait services-stable` (timeout 10 min)
   - Smoke test: `curl -f http://<bastion-proxy>/health` — skipped in workflow (internal ALB not reachable from GitHub runners); stability wait is the deploy gate

Trigger: `workflow_dispatch` only (no auto-deploy on push).

**New GitHub Actions variables required:**

| Variable | Value (post-apply) |
|---|---|
| `MDG_ECR_REPO_URL` | `module.fargate_mdg.mdg_ecr_repo_url` output |
| `MDG_ECS_CLUSTER` | `module.fargate_mdg.mdg_cluster_name` output |
| `MDG_ECS_SERVICE` | `module.fargate_mdg.mdg_service_name` output |

### New script: `scripts/deploy_mdg_fargate.sh`

Mirrors `deploy_fargate.sh`. Required env vars: `MDG_ECR_REPO_URL`, `MDG_ECS_CLUSTER`, `MDG_ECS_SERVICE`.

```bash
docker build -f "$ROOT_DIR/mdg/Dockerfile" -t mdg:latest "$ROOT_DIR/mdg"
docker tag mdg:latest "$REPO:latest"
docker push "$REPO:latest"
aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" \
  --desired-count 1 --force-new-deployment --region "$REGION" --output json > /dev/null
```

---

## Deployment Steps (manual, one-time)

1. `terraform -chdir=terraform/envs/dev init` (new module)
2. `terraform -chdir=terraform/envs/dev plan` — verify new resources, no newsletter changes
3. `terraform -chdir=terraform/envs/dev apply`
4. Copy `mdg_alb_dns` output → update `config/dev.yaml` `mdg.url`
5. Push MDG image: `MDG_ECR_REPO_URL=<output> MDG_ECS_CLUSTER=<output> MDG_ECS_SERVICE=<output> ./scripts/deploy_mdg_fargate.sh`
6. Set newsletter GitHub Actions vars: `MDG_ECR_REPO_URL`, `MDG_ECS_CLUSTER`, `MDG_ECS_SERVICE`
7. Redeploy newsletter so it picks up new `config/dev.yaml`

---

## Out of Scope

- HTTPS/TLS on internal ALB (VPC-internal, HTTP sufficient)
- MDG public ALB (MDG is never publicly exposed)
- Cognito/JWT on MDG (FastAPI owns auth; MDG trusts `X-User-Id` header)
