# MDG Fargate Deployment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the MDG PHP Symfony 7 service to AWS Fargate with PHP-FPM + nginx, exposed via an internal ALB to the newsletter FastAPI service.

**Architecture:** New `terraform/modules/fargate-mdg/` module creates an isolated ECS Fargate service (512 CPU / 1024 MB, max 2 tasks) with PHP-FPM + nginx in one container, connected to the existing Aurora PostgreSQL and ElastiCache Redis. The newsletter FastAPI service communicates with MDG via a VPC-internal ALB (port 80 → container port 9000). DATABASE_URL and APP_SECRET are stored in Secrets Manager and injected at task start.

**Tech Stack:** PHP 8.4, Symfony 7, PHP-FPM, nginx (Alpine), supervisord, Terraform (AWS + random providers), GitHub Actions (`shivammathur/setup-php`), ECR, ECS Fargate, Secrets Manager, internal ALB, Auto Scaling.

---

## File Map

| Action | File | Purpose |
|---|---|---|
| Create | `mdg/docker/nginx.conf` | nginx: HTTP on 9000, fastcgi_pass to 127.0.0.1:9001 |
| Create | `mdg/docker/www.conf` | PHP-FPM pool: listen 127.0.0.1:9001, pm.max_children=10 |
| Create | `mdg/docker/supervisord.conf` | supervisord: manages nginx + php-fpm processes |
| Modify | `mdg/Dockerfile` | Replace `php:8.4-cli-alpine` + `php -S` with fpm-alpine + nginx + supervisord |
| Create | `terraform/modules/fargate-mdg/variables.tf` | Module input variables |
| Create | `terraform/modules/fargate-mdg/outputs.tf` | Module outputs (ALB DNS, ECR URL, cluster/service names, SG IDs) |
| Create | `terraform/modules/fargate-mdg/main.tf` | All MDG infra: ECR, ECS, IAM, secrets, SGs, internal ALB, task def, service, auto-scaling |
| Modify | `terraform/modules/fargate/outputs.tf` | Add `fargate_sg_id` output (needed by cross-module SG rule) |
| Modify | `terraform/envs/dev/main.tf` | Add `module "fargate_mdg"` + cross-module SG rule |
| Modify | `terraform/envs/dev/outputs.tf` | Add MDG outputs |
| Create | `scripts/deploy_mdg_fargate.sh` | Build + push ECR + force ECS redeploy |
| Create | `.github/workflows/mdg-fargate-deploy.yml` | PHPUnit + ECR push + ECS deploy |

---

## Task 1: Fix MDG Dockerfile — PHP-FPM + nginx + supervisord

The current `mdg/Dockerfile` uses `php:8.4-cli-alpine` + `php -S` (single-threaded dev server, unsuitable for production). This task replaces it with PHP-FPM (multi-process, bounded connection count) + nginx (HTTP→FastCGI proxy) + supervisord (process manager for both).

**Why two ports:** PHP-FPM speaks FastCGI (port 9001 internally). nginx speaks HTTP (port 9000, the container port). The ALB sends HTTP to port 9000; nginx translates to FastCGI and forwards to PHP-FPM on 9001.

**Files:**
- Create: `mdg/docker/nginx.conf`
- Create: `mdg/docker/www.conf`
- Create: `mdg/docker/supervisord.conf`
- Modify: `mdg/Dockerfile`

---

- [ ] **Step 1: Create `mdg/docker/nginx.conf`**

```nginx
worker_processes auto;
error_log /dev/stderr warn;
pid /tmp/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include      /etc/nginx/mime.types;
    default_type application/octet-stream;
    access_log   /dev/stdout;

    server {
        listen 9000;
        root /app/public;

        location / {
            try_files $uri /index.php$is_args$args;
        }

        location ~ ^/index\.php(/|$) {
            fastcgi_pass 127.0.0.1:9001;
            fastcgi_split_path_info ^(.+\.php)(/.*)$;
            include fastcgi_params;
            fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
            fastcgi_param DOCUMENT_ROOT $document_root;
            internal;
        }

        location ~ \.php$ {
            return 404;
        }
    }
}
```

- [ ] **Step 2: Create `mdg/docker/www.conf`**

This replaces the default PHP-FPM pool. `pm.max_children = 10` means 2 Fargate tasks = 20 DB connections, within the `db.t3.micro` limit (~110).

```ini
[www]
user = www-data
group = www-data
listen = 127.0.0.1:9001
pm = dynamic
pm.max_children = 10
pm.start_servers = 2
pm.min_spare_servers = 1
pm.max_spare_servers = 4
pm.max_requests = 500
```

- [ ] **Step 3: Create `mdg/docker/supervisord.conf`**

```ini
[supervisord]
nodaemon=true
user=root
logfile=/dev/null
logfile_maxbytes=0
pidfile=/tmp/supervisord.pid

[program:php-fpm]
command=/usr/local/sbin/php-fpm -F
autostart=true
autorestart=true
priority=1
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:nginx]
command=/usr/sbin/nginx -g "daemon off;"
autostart=true
autorestart=true
priority=10
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
```

- [ ] **Step 4: Update `mdg/Dockerfile`**

Replace the entire file:

```dockerfile
FROM php:8.4-fpm-alpine

RUN apk add --no-cache nginx supervisor postgresql-dev \
    && docker-php-ext-install pdo pdo_pgsql opcache \
    && echo "opcache.enable=1\nopcache.memory_consumption=128\nopcache.max_accelerated_files=10000\nopcache.revalidate_freq=60" \
       > /usr/local/etc/php/conf.d/opcache.ini

# zz-docker.conf in the base image overrides listen to 0.0.0.0:9000; remove it
# so our www.conf (port 9001) takes effect without conflict with nginx on 9000
RUN rm -f /usr/local/etc/php-fpm.d/zz-docker.conf

WORKDIR /app

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

COPY composer.json ./
RUN composer install --no-dev --optimize-autoloader --no-interaction

COPY . .

RUN composer dump-autoload --optimize \
    && mkdir -p var/cache var/log \
    && chown -R www-data:www-data /app/var

COPY docker/www.conf /usr/local/etc/php-fpm.d/www.conf
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/supervisord.conf /etc/supervisord.conf

EXPOSE 9000
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]
```

- [ ] **Step 5: Verify the build succeeds**

Run from the repo root:

```bash
docker build -f mdg/Dockerfile -t mdg-test ./mdg
```

Expected: build completes with no errors, final line is `Successfully built <id>` or `naming to docker.io/library/mdg-test`.

If the build fails at `composer install`, ensure you have internet access in Docker (needed to pull packages).

- [ ] **Step 6: Commit**

```bash
git add mdg/Dockerfile mdg/docker/
git commit -m "infra(mdg): replace php -S dev server with PHP-FPM + nginx + supervisord"
```

---

## Task 2: Terraform fargate-mdg module — variables.tf and outputs.tf

Creates the module skeleton with all inputs and outputs declared. No resources yet (that's Task 3). This order lets you catch naming mistakes before writing 200 lines of resources.

**Files:**
- Create: `terraform/modules/fargate-mdg/variables.tf`
- Create: `terraform/modules/fargate-mdg/outputs.tf`

---

- [ ] **Step 1: Create `terraform/modules/fargate-mdg/variables.tf`**

```hcl
variable "name_prefix" {
  type    = string
  default = "newsletter-mdg"
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "aurora_sg_id" {
  type        = string
  description = "Existing aurora SG — module adds ingress rule 5432 from MDG fargate SG"
}

variable "redis_sg_id" {
  type        = string
  description = "Existing redis SG — module adds ingress rule 6379 from MDG fargate SG"
}

variable "newsletter_fargate_sg_id" {
  type        = string
  description = "Newsletter fargate SG — internal ALB allows ingress 80 from it"
}

variable "db_host" {
  type        = string
  description = "DB hostname. Free tier: module.aurora.cluster_endpoint. Premium: module.aurora.rds_proxy_endpoint."
}

variable "db_name" {
  type    = string
  default = "newsletter"
}

variable "db_user" {
  type    = string
  default = "newsletter"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "redis_endpoint" {
  type = string
}

variable "region" {
  type    = string
  default = "eu-west-1"
}

variable "image_tag" {
  type    = string
  default = "latest"
}
```

- [ ] **Step 2: Create `terraform/modules/fargate-mdg/outputs.tf`**

```hcl
output "mdg_alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "mdg_ecr_repo_url" {
  value = aws_ecr_repository.main.repository_url
}

output "mdg_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "mdg_service_name" {
  value = aws_ecs_service.main.name
}

output "mdg_fargate_sg_id" {
  value = aws_security_group.mdg_fargate.id
}

output "mdg_internal_alb_sg_id" {
  value = aws_security_group.internal_alb.id
}
```

- [ ] **Step 3: Commit**

```bash
git add terraform/modules/fargate-mdg/
git commit -m "infra(mdg): add fargate-mdg terraform module scaffold (variables + outputs)"
```

---

## Task 3: Terraform fargate-mdg module — main.tf

Creates all AWS resources for the MDG Fargate service. Follow the existing `terraform/modules/fargate/main.tf` pattern: all SG rules as separate `aws_security_group_rule` resources (no inline rules on SGs that other modules reference).

**Key differences from the newsletter fargate module:**
- Internal ALB (`internal = true`, private subnets) instead of public
- Port 9000 (not 8000)
- Smaller task: 512 CPU / 1024 MB
- DATABASE_URL and APP_SECRET stored as full Secrets Manager secrets (not JSON fields)
- `random_password` for APP_SECRET generation

**File:**
- Create: `terraform/modules/fargate-mdg/main.tf`

---

- [ ] **Step 1: Create `terraform/modules/fargate-mdg/main.tf`**

```hcl
resource "aws_ecr_repository" "main" {
  name         = var.name_prefix
  force_delete = true
}

resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"
}

resource "aws_cloudwatch_log_group" "main" {
  name              = "/ecs/${var.name_prefix}"
  retention_in_days = 7
}

resource "aws_iam_role" "execution" {
  name = "${var.name_prefix}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "random_password" "app_secret" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "app_secret" {
  name = "${var.name_prefix}/app-secret"
}

resource "aws_secretsmanager_secret_version" "app_secret" {
  secret_id     = aws_secretsmanager_secret.app_secret.id
  secret_string = random_password.app_secret.result
}

resource "aws_secretsmanager_secret" "db_url" {
  name = "${var.name_prefix}/db-url"
}

resource "aws_secretsmanager_secret_version" "db_url" {
  secret_id = aws_secretsmanager_secret.db_url.id
  secret_string = format(
    "postgresql://%s:%s@%s/%s?serverVersion=15&charset=utf8",
    var.db_user, var.db_password, var.db_host, var.db_name
  )
}

resource "aws_iam_role_policy" "execution_secrets" {
  name = "${var.name_prefix}-ecs-secrets"
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [
        aws_secretsmanager_secret.db_url.arn,
        aws_secretsmanager_secret.app_secret.arn,
      ]
    }]
  })
}

# Internal ALB security group — no inline rules
resource "aws_security_group" "internal_alb" {
  name        = "${var.name_prefix}-internal-alb-sg"
  description = "MDG internal ALB"
  vpc_id      = var.vpc_id
}

resource "aws_security_group_rule" "internal_alb_ingress_newsletter" {
  type                     = "ingress"
  from_port                = 80
  to_port                  = 80
  protocol                 = "tcp"
  security_group_id        = aws_security_group.internal_alb.id
  source_security_group_id = var.newsletter_fargate_sg_id
}

resource "aws_security_group_rule" "internal_alb_egress_all" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.internal_alb.id
}

# MDG Fargate security group — no inline rules
resource "aws_security_group" "mdg_fargate" {
  name        = "${var.name_prefix}-fargate-sg"
  description = "MDG Fargate tasks"
  vpc_id      = var.vpc_id
}

resource "aws_security_group_rule" "mdg_ingress_alb" {
  type                     = "ingress"
  from_port                = 9000
  to_port                  = 9000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.mdg_fargate.id
  source_security_group_id = aws_security_group.internal_alb.id
}

resource "aws_security_group_rule" "mdg_egress_https" {
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.mdg_fargate.id
}

resource "aws_security_group_rule" "mdg_egress_aurora" {
  type                     = "egress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.mdg_fargate.id
  source_security_group_id = var.aurora_sg_id
}

resource "aws_security_group_rule" "mdg_egress_redis" {
  type                     = "egress"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  security_group_id        = aws_security_group.mdg_fargate.id
  source_security_group_id = var.redis_sg_id
}

# Add ingress rules to existing shared SGs
resource "aws_security_group_rule" "aurora_ingress_mdg" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = var.aurora_sg_id
  source_security_group_id = aws_security_group.mdg_fargate.id
}

resource "aws_security_group_rule" "redis_ingress_mdg" {
  type                     = "ingress"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  security_group_id        = var.redis_sg_id
  source_security_group_id = aws_security_group.mdg_fargate.id
}

resource "aws_lb" "main" {
  name               = "${var.name_prefix}-internal-alb"
  load_balancer_type = "application"
  internal           = true
  security_groups    = [aws_security_group.internal_alb.id]
  subnets            = var.private_subnet_ids
}

resource "aws_lb_target_group" "main" {
  name        = "${var.name_prefix}-tg"
  port        = 9000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    interval            = 30
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "main" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.main.arn
  }
}

resource "aws_ecs_task_definition" "main" {
  family                   = var.name_prefix
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution.arn

  container_definitions = jsonencode([{
    name  = "mdg"
    image = "${aws_ecr_repository.main.repository_url}:${var.image_tag}"
    portMappings = [{ containerPort = 9000, hostPort = 9000, protocol = "tcp" }]
    environment = [
      { name = "APP_ENV",   value = "prod" },
      { name = "REDIS_URL", value = "redis://${var.redis_endpoint}" },
    ]
    secrets = [
      { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.db_url.arn },
      { name = "APP_SECRET",   valueFrom = aws_secretsmanager_secret.app_secret.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.main.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
}

resource "aws_ecs_service" "main" {
  name            = "${var.name_prefix}-svc"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.main.arn
  desired_count   = 0
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.mdg_fargate.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.main.arn
    container_name   = "mdg"
    container_port   = 9000
  }

  lifecycle {
    ignore_changes = [desired_count, task_definition]
  }

  depends_on = [aws_lb_listener.main]
}

resource "aws_appautoscaling_target" "main" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.main.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = 0
  max_capacity       = 2

  depends_on = [aws_ecs_service.main]
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "${var.name_prefix}-cpu-scaling"
  service_namespace  = "ecs"
  resource_id        = aws_appautoscaling_target.main.resource_id
  scalable_dimension = aws_appautoscaling_target.main.scalable_dimension
  policy_type        = "TargetTrackingScaling"

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add terraform/modules/fargate-mdg/main.tf
git commit -m "infra(mdg): add fargate-mdg terraform module main.tf"
```

---

## Task 4: Wire fargate-mdg into dev environment + validate

Connects the new module to the dev environment. Adds a `fargate_sg_id` output to the existing fargate module (needed for the cross-module egress rule), adds the `fargate_mdg` module call, and adds MDG outputs.

**Files:**
- Modify: `terraform/modules/fargate/outputs.tf`
- Modify: `terraform/envs/dev/main.tf`
- Modify: `terraform/envs/dev/outputs.tf`

---

- [ ] **Step 1: Add `fargate_sg_id` to `terraform/modules/fargate/outputs.tf`**

Append to the end of the existing file (which already has alb_dns, ecr_repo_url, cluster_name, service_name):

```hcl
output "fargate_sg_id" {
  value = aws_security_group.fargate.id
}
```

- [ ] **Step 2: Add module + cross-SG rule to `terraform/envs/dev/main.tf`**

Append to the end of the existing file (after the existing `module "fargate"` block):

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

# Newsletter Fargate → MDG internal ALB (port 80)
resource "aws_security_group_rule" "newsletter_egress_mdg_alb" {
  type                     = "egress"
  from_port                = 80
  to_port                  = 80
  protocol                 = "tcp"
  security_group_id        = module.fargate.fargate_sg_id
  source_security_group_id = module.fargate_mdg.mdg_internal_alb_sg_id
}
```

- [ ] **Step 3: Add MDG outputs to `terraform/envs/dev/outputs.tf`**

Append to the end of the existing file:

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

- [ ] **Step 4: Run terraform init + validate**

```bash
terraform -chdir=terraform/envs/dev init
terraform -chdir=terraform/envs/dev validate
```

Expected output: `Success! The configuration is valid.`

If `init` fails on downloading providers, ensure you have internet access. If `validate` fails with "Reference to undeclared resource", double-check the resource names in `fargate-mdg/main.tf` match what `outputs.tf` references (e.g., `aws_lb.main`, `aws_ecs_cluster.main`, `aws_security_group.mdg_fargate`, `aws_security_group.internal_alb`).

- [ ] **Step 5: Commit**

```bash
git add terraform/modules/fargate/outputs.tf terraform/envs/dev/main.tf terraform/envs/dev/outputs.tf
git commit -m "infra(mdg): wire fargate-mdg module into dev environment"
```

---

## Task 5: Deploy script

Mirrors `scripts/deploy_fargate.sh` exactly but targets MDG environment variables and build path. Required env vars: `MDG_ECR_REPO_URL`, `MDG_ECS_CLUSTER`, `MDG_ECS_SERVICE`.

**File:**
- Create: `scripts/deploy_mdg_fargate.sh`

---

- [ ] **Step 1: Create `scripts/deploy_mdg_fargate.sh`**

```bash
#!/usr/bin/env bash
# Build MDG Docker image, push to ECR, force ECS service redeployment.
# Required env vars: MDG_ECR_REPO_URL, MDG_ECS_CLUSTER, MDG_ECS_SERVICE
# Optional: AWS_DEFAULT_REGION (default: eu-west-1)
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-eu-west-1}"
REPO="${MDG_ECR_REPO_URL:?MDG_ECR_REPO_URL is required}"
CLUSTER="${MDG_ECS_CLUSTER:?MDG_ECS_CLUSTER is required}"
SERVICE="${MDG_ECS_SERVICE:?MDG_ECS_SERVICE is required}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== ECR login ===" >&2
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${REPO%%/*}"

echo "=== docker build ===" >&2
docker build -f "$ROOT_DIR/mdg/Dockerfile" -t mdg:latest "$ROOT_DIR/mdg"

echo "=== docker tag + push ===" >&2
docker tag mdg:latest "$REPO:latest"
docker push "$REPO:latest"

echo "=== force ECS redeployment (latest task definition) ===" >&2
LATEST_TASK_DEF=$(aws ecs describe-task-definition \
  --task-definition "${SERVICE%-svc}" \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text \
  --region "$REGION")
echo "Task definition: $LATEST_TASK_DEF" >&2
aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --task-definition "$LATEST_TASK_DEF" \
  --force-new-deployment \
  --region "$REGION" \
  --output json > /dev/null

echo "Deploy triggered. Tasks will cycle with new image + task definition." >&2
```

- [ ] **Step 2: Make executable and syntax-check**

```bash
chmod +x scripts/deploy_mdg_fargate.sh
bash -n scripts/deploy_mdg_fargate.sh
```

Expected: no output (clean syntax).

- [ ] **Step 3: Commit**

```bash
git add scripts/deploy_mdg_fargate.sh
git commit -m "infra(mdg): add deploy_mdg_fargate.sh deploy script"
```

---

## Task 6: CI/CD Workflow

Mirrors `.github/workflows/fargate-deploy.yml`. Two jobs: `test` (PHPUnit) and `deploy` (ECR push + ECS update). Trigger: `workflow_dispatch` only — no auto-deploy on push.

Required GitHub Actions variables (set after `terraform apply`):
- `MDG_ECR_REPO_URL` — from `mdg_ecr_repo_url` terraform output
- `MDG_ECS_CLUSTER` — from `mdg_ecs_cluster` terraform output
- `MDG_ECS_SERVICE` — from `mdg_ecs_service` terraform output
- `AWS_ROLE_ARN` — already exists for the newsletter workflow

**File:**
- Create: `.github/workflows/mdg-fargate-deploy.yml`

---

- [ ] **Step 1: Create `.github/workflows/mdg-fargate-deploy.yml`**

```yaml
name: MDG Fargate Deploy

on:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Set up PHP 8.4
        uses: shivammathur/setup-php@v2
        with:
          php-version: "8.4"
          extensions: pdo_pgsql

      - name: Install dependencies
        working-directory: mdg
        run: composer install --optimize-autoloader --no-interaction

      - name: Run PHPUnit
        working-directory: mdg
        run: vendor/bin/phpunit

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
                "$(echo "${{ vars.MDG_ECR_REPO_URL }}" | cut -d/ -f1)"

      - name: Build and push Docker image
        run: |
          docker build -f mdg/Dockerfile -t "${{ vars.MDG_ECR_REPO_URL }}:latest" ./mdg
          docker push "${{ vars.MDG_ECR_REPO_URL }}:latest"

      - name: Force ECS redeployment
        run: |
          aws ecs update-service \
            --cluster "${{ vars.MDG_ECS_CLUSTER }}" \
            --service "${{ vars.MDG_ECS_SERVICE }}" \
            --desired-count 1 \
            --force-new-deployment \
            --region eu-west-1 \
            --output json > /dev/null

      - name: Wait for service stable
        timeout-minutes: 10
        run: |
          aws ecs wait services-stable \
            --cluster "${{ vars.MDG_ECS_CLUSTER }}" \
            --services "${{ vars.MDG_ECS_SERVICE }}" \
            --region eu-west-1
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import sys, yaml; yaml.safe_load(open('.github/workflows/mdg-fargate-deploy.yml'))" && echo "YAML valid"
```

Expected: `YAML valid`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/mdg-fargate-deploy.yml
git commit -m "ci(mdg): add mdg-fargate-deploy workflow (PHPUnit + ECR + ECS)"
```

---

## Post-Implementation: Manual Deployment Steps

After all tasks are complete, follow these steps to bring MDG live. These are one-time manual operations, not code tasks.

**1. Terraform apply**
```bash
terraform -chdir=terraform/envs/dev init
terraform -chdir=terraform/envs/dev plan   # verify only MDG resources, no newsletter changes
terraform -chdir=terraform/envs/dev apply
```

**2. Capture outputs**
```bash
terraform -chdir=terraform/envs/dev output mdg_alb_dns
terraform -chdir=terraform/envs/dev output mdg_ecr_repo_url
terraform -chdir=terraform/envs/dev output mdg_ecs_cluster
terraform -chdir=terraform/envs/dev output mdg_ecs_service
```

**3. Push first MDG image**
```bash
export MDG_ECR_REPO_URL=<mdg_ecr_repo_url output>
export MDG_ECS_CLUSTER=<mdg_ecs_cluster output>
export MDG_ECS_SERVICE=<mdg_ecs_service output>
./scripts/deploy_mdg_fargate.sh
```

**4. Run Doctrine migrations** (one-time schema setup)

MDG owns the schema via Doctrine. Run the migration as a one-off ECS task after the first image push:
```bash
aws ecs run-task \
  --cluster "$MDG_ECS_CLUSTER" \
  --task-definition newsletter-mdg \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<private-subnet-id>],securityGroups=[<mdg-fargate-sg-id>],assignPublicIp=DISABLED}" \
  --overrides '{"containerOverrides":[{"name":"mdg","command":["php","bin/console","doctrine:migrations:migrate","--no-interaction"]}]}' \
  --region eu-west-1
```

Get the subnet ID and SG ID from Terraform outputs / AWS console.

**5. Update `config/dev.yaml`**

Replace the placeholder MDG URL with the real internal ALB DNS:
```yaml
mdg:
  url: "http://<mdg_alb_dns output>"
```

**6. Set GitHub Actions variables** (for future CI/CD deploys)
- `MDG_ECR_REPO_URL`
- `MDG_ECS_CLUSTER`
- `MDG_ECS_SERVICE`

**7. Redeploy newsletter** so it picks up the updated `config/dev.yaml` with the real MDG URL.
