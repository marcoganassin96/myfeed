# Restore Premium Infrastructure (Aurora Serverless v2 + RDS Proxy)

## Context

Branch: `infra/terraform-aws-infrastructure`  
Worktree: `.worktrees/infra/terraform-aws-infrastructure`

The current infra uses a **free-tier downgrade**:
- `terraform/modules/aurora/main.tf` → `aws_db_instance` (RDS PostgreSQL db.t3.micro)
- RDS Proxy removed entirely
- `min_capacity` / `max_capacity` variables removed

Target state (premium):
- `aws_rds_cluster` + `aws_rds_cluster_instance` (Aurora Serverless v2)
- `aws_db_proxy` in front of Aurora (connection pooling)
- IAM role for proxy secret access
- `rds_proxy_endpoint` output wired through to Lambda

**Also note:** `scripts/deploy.sh` already reads `rds_proxy_endpoint` (line 14), but `terraform/envs/dev/outputs.tf` currently exports `cluster_endpoint` instead. This is a latent bug fixed as part of this upgrade.

---

## Files to Change

### 1. `terraform/modules/aurora/main.tf`

Replace the entire file with:

```hcl
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "db" {
  name                    = "${var.name_prefix}-db-password"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    username = var.db_user
    password = random_password.db.result
  })
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.name_prefix}-aurora-subnet-group"
  subnet_ids = var.subnet_ids
}

resource "aws_rds_cluster" "main" {
  cluster_identifier     = "${var.name_prefix}-aurora"
  engine                 = "aurora-postgresql"
  engine_mode            = "provisioned"
  engine_version         = "15.4"
  database_name          = var.db_name
  master_username        = var.db_user
  master_password        = random_password.db.result
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.security_group_id]
  skip_final_snapshot    = true
  deletion_protection    = false

  serverlessv2_scaling_configuration {
    min_capacity = var.min_capacity
    max_capacity = var.max_capacity
  }
}

resource "aws_rds_cluster_instance" "writer" {
  identifier         = "${var.name_prefix}-aurora-writer"
  cluster_identifier = aws_rds_cluster.main.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.main.engine
  engine_version     = aws_rds_cluster.main.engine_version
}

resource "aws_iam_role" "rds_proxy" {
  name = "${var.name_prefix}-rds-proxy-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "rds.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "rds_proxy_secrets" {
  name = "${var.name_prefix}-rds-proxy-secrets"
  role = aws_iam_role.rds_proxy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [aws_secretsmanager_secret.db.arn]
    }]
  })
}

resource "aws_db_proxy" "main" {
  name                   = "${var.name_prefix}-rds-proxy"
  debug_logging          = false
  engine_family          = "POSTGRESQL"
  idle_client_timeout    = 1800
  require_tls            = false
  role_arn               = aws_iam_role.rds_proxy.arn
  vpc_security_group_ids = [var.security_group_id]
  vpc_subnet_ids         = var.subnet_ids

  auth {
    auth_scheme = "SECRETS"
    iam_auth    = "DISABLED"
    secret_arn  = aws_secretsmanager_secret.db.arn
  }
}

resource "aws_db_proxy_default_target_group" "main" {
  db_proxy_name = aws_db_proxy.main.name

  connection_pool_config {
    max_connections_percent = 100
  }
}

resource "aws_db_proxy_target" "main" {
  db_cluster_identifier = aws_rds_cluster.main.cluster_identifier
  db_proxy_name         = aws_db_proxy.main.name
  target_group_name     = aws_db_proxy_default_target_group.main.name
}
```

---

### 2. `terraform/modules/aurora/variables.tf`

Replace the entire file with:

```hcl
variable "name_prefix" {
  type    = string
  default = "newsletter"
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "db_name" {
  type    = string
  default = "newsletter"
}

variable "db_user" {
  type    = string
  default = "newsletter"
}

variable "min_capacity" {
  type    = number
  default = 0.5
}

variable "max_capacity" {
  type    = number
  default = 16
}
```

---

### 3. `terraform/modules/aurora/outputs.tf`

Replace the entire file with:

```hcl
output "rds_proxy_endpoint" {
  value = aws_db_proxy.main.endpoint
}

output "db_name" {
  value = var.db_name
}

output "db_user" {
  value = var.db_user
}

output "db_password" {
  value     = random_password.db.result
  sensitive = true
}

output "secret_arn" {
  value = aws_secretsmanager_secret.db.arn
}
```

---

### 4. `terraform/envs/dev/variables.tf`

Replace the entire file with:

```hcl
variable "region" {
  type    = string
  default = "eu-west-1"
}

variable "name_prefix" {
  type    = string
  default = "newsletter-dev"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "azs" {
  type    = list(string)
  default = ["eu-west-1a", "eu-west-1b"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.101.0/24", "10.0.102.0/24"]
}

variable "db_name" {
  type    = string
  default = "newsletter"
}

variable "db_user" {
  type    = string
  default = "newsletter"
}

variable "aurora_min_capacity" {
  type    = number
  default = 0.5
}

variable "aurora_max_capacity" {
  type    = number
  default = 16
}
```

---

### 5. `terraform/envs/dev/main.tf`

Replace the `module "aurora"` block only. Full file:

```hcl
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.region
}

module "vpc" {
  source               = "../../modules/vpc"
  name_prefix          = var.name_prefix
  vpc_cidr             = var.vpc_cidr
  azs                  = var.azs
  private_subnet_cidrs = var.private_subnet_cidrs
  public_subnet_cidrs  = var.public_subnet_cidrs
}

module "aurora" {
  source            = "../../modules/aurora"
  name_prefix       = var.name_prefix
  vpc_id            = module.vpc.vpc_id
  subnet_ids        = module.vpc.private_subnet_ids
  security_group_id = module.vpc.aurora_sg_id
  db_name           = var.db_name
  db_user           = var.db_user
  min_capacity      = var.aurora_min_capacity
  max_capacity      = var.aurora_max_capacity
}

module "redis" {
  source            = "../../modules/redis"
  name_prefix       = var.name_prefix
  subnet_ids        = module.vpc.private_subnet_ids
  security_group_id = module.vpc.redis_sg_id
}
```

---

### 6. `terraform/envs/dev/outputs.tf`

Replace the entire file with:

```hcl
output "vpc_id" {
  value = module.vpc.vpc_id
}

output "private_subnet_ids_csv" {
  value = module.vpc.private_subnet_ids_csv
}

output "lambda_sg_id" {
  value = module.vpc.lambda_sg_id
}

output "rds_proxy_endpoint" {
  value = module.aurora.rds_proxy_endpoint
}

output "redis_endpoint" {
  value = module.redis.redis_endpoint
}

output "db_password" {
  value     = module.aurora.db_password
  sensitive = true
}

output "db_name" {
  value = module.aurora.db_name
}

output "db_user" {
  value = module.aurora.db_user
}
```

---

### 7. `scripts/deploy.sh` — no change needed

Already reads `rds_proxy_endpoint` on line 14. No edits required.

---

## Apply

```bash
cd terraform/envs/dev
terraform init   # only needed if provider lock changed
terraform plan   # verify: expect destroy aws_db_instance, create aws_rds_cluster + proxy resources
terraform apply
```

Proxy creation takes ~5 minutes. After apply, `DB_HOST` in Lambda env automatically points to proxy endpoint via `deploy.sh`.

```bash
cd ../../..
./scripts/deploy.sh
```

---

## Commit

```
infra(aurora): restore Aurora Serverless v2 and RDS Proxy
```
