# Terraform AWS Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provision VPC, Aurora Serverless v2, and ElastiCache Serverless via Terraform so `scripts/deploy.sh` can call `sam deploy` with all required parameters.

---

## Free Tier Constraints (dev environment)

| Resource | Free Tier Constraint | Applied |
|---|---|---|
| Aurora Serverless v2 | max 4 ACUs | `aurora_max_capacity = 4` |
| RDS Proxy | **not available** on free tier accounts | Removed — Lambda connects to cluster endpoint directly |
| ElastiCache Serverless | not free tier eligible — small usage cost | Keep; no free alternative |

**Connection pooling risk without proxy:** At >200 concurrent Lambda VUs Aurora may exhaust `max_connections` (~90 at 4 ACU). Mitigate with module-level psycopg2 connection singleton (reused across warm invocations). Accept the risk for dev/load-test; add proxy before production.

**Architecture:** Three reusable modules (vpc, aurora, redis) called from `terraform/envs/dev/`. A bootstrap step provisions the S3 state bucket and DynamoDB lock table once. The SAM template is updated to accept a Terraform-managed Lambda security group ID instead of creating its own. `scripts/deploy.sh` reads Terraform outputs and calls `sam deploy` non-interactively.

**Tech Stack:** Terraform ≥ 1.6, AWS provider ~> 5.0, random provider ~> 3.0, AWS SAM CLI, AWS CLI

---

## Pre-requisites

- Terraform ≥ 1.6 installed (`terraform -version`)
- AWS CLI configured with credentials for the target account (`aws sts get-caller-identity`)
- AWS SAM CLI installed (`sam --version`)
- Working directory: project root (`d:\Marco\apps\python-newsletter`)

---

## File Map

| File | Responsibility |
|---|---|
| `terraform/bootstrap/main.tf` | S3 state bucket + DynamoDB lock table (run once) |
| `terraform/bootstrap/outputs.tf` | Print bucket name and table name |
| `terraform/modules/vpc/main.tf` | VPC, subnets, IGW, NAT GW, route tables, 3 security groups |
| `terraform/modules/vpc/variables.tf` | VPC input variables with defaults |
| `terraform/modules/vpc/outputs.tf` | vpc_id, subnet IDs, security group IDs |
| `terraform/modules/aurora/main.tf` | Aurora Serverless v2, Secrets Manager (no RDS Proxy — free tier) |
| `terraform/modules/aurora/variables.tf` | Aurora input variables (`max_capacity` capped at 4 for free tier) |
| `terraform/modules/aurora/outputs.tf` | cluster_endpoint, db_password (sensitive), db_name, db_user |
| `terraform/modules/redis/main.tf` | ElastiCache Serverless cluster |
| `terraform/modules/redis/variables.tf` | Redis input variables |
| `terraform/modules/redis/outputs.tf` | redis_endpoint, redis_port |
| `terraform/envs/dev/backend.tf` | S3 backend config (fill account ID after bootstrap) |
| `terraform/envs/dev/main.tf` | Root module: calls all 3 modules, declares provider |
| `terraform/envs/dev/variables.tf` | Environment-level variables with dev defaults |
| `terraform/envs/dev/outputs.tf` | Top-level outputs mapping to SAM parameters |
| `terraform/envs/dev/terraform.tfvars.example` | Committed example; actual tfvars gitignored |
| `infra/template.yaml` | **Modified:** remove `LambdaSG` resource, add `LambdaSecurityGroupId` parameter |
| `scripts/deploy.sh` | Read TF outputs → `sam deploy` |

---

### Task 1: Update .gitignore for Terraform Artifacts

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add Terraform entries to `.gitignore`**

Append to `.gitignore`:

```
# Terraform
.terraform/
*.tfstate
*.tfstate.backup
terraform.tfvars
*.tfvars.json
```

Note: `.terraform.lock.hcl` is intentionally NOT ignored — commit it for reproducible provider versions.

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: add Terraform artifacts to .gitignore"
```

---

### Task 2: Bootstrap Module

**Files:**
- Create: `terraform/bootstrap/main.tf`
- Create: `terraform/bootstrap/outputs.tf`

The bootstrap creates the S3 bucket and DynamoDB table used as the Terraform backend for all environments. Its own state is intentionally local (stored in `terraform/bootstrap/terraform.tfstate`).

- [ ] **Step 1: Create `terraform/bootstrap/main.tf`**

```hcl
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "eu-west-1"
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "tfstate" {
  bucket = "newsletter-tfstate-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "tfstate_lock" {
  name         = "newsletter-tfstate-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}
```

- [ ] **Step 2: Create `terraform/bootstrap/outputs.tf`**

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
```

- [ ] **Step 3: Validate**

```bash
cd terraform/bootstrap
terraform init
terraform validate
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 4: Commit**

```bash
cd ../..
git add terraform/bootstrap/
git commit -m "infra(terraform): bootstrap S3 state bucket and DynamoDB lock table"
```

---

### Task 3: VPC Module

**Files:**
- Create: `terraform/modules/vpc/variables.tf`
- Create: `terraform/modules/vpc/main.tf`
- Create: `terraform/modules/vpc/outputs.tf`

- [ ] **Step 1: Create `terraform/modules/vpc/variables.tf`**

```hcl
variable "name_prefix" {
  type    = string
  default = "newsletter"
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
```

- [ ] **Step 2: Create `terraform/modules/vpc/main.tf`**

```hcl
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "${var.name_prefix}-vpc" }
}

resource "aws_subnet" "private" {
  count             = length(var.azs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.azs[count.index]

  tags = { Name = "${var.name_prefix}-private-${var.azs[count.index]}" }
}

resource "aws_subnet" "public" {
  count                   = length(var.azs)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = true

  tags = { Name = "${var.name_prefix}-public-${var.azs[count.index]}" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.name_prefix}-igw" }
}

resource "aws_eip" "nat" {
  domain = "vpc"
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  depends_on    = [aws_internet_gateway.main]
  tags          = { Name = "${var.name_prefix}-nat" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "${var.name_prefix}-public-rt" }
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }
  tags = { Name = "${var.name_prefix}-private-rt" }
}

resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

resource "aws_security_group" "lambda" {
  name        = "${var.name_prefix}-lambda-sg"
  description = "Lambda functions outbound to Aurora and Redis"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "aurora" {
  name        = "${var.name_prefix}-aurora-sg"
  description = "Aurora PostgreSQL ingress from Lambda only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }
}

resource "aws_security_group" "redis" {
  name        = "${var.name_prefix}-redis-sg"
  description = "Redis ingress from Lambda only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }
}
```

- [ ] **Step 3: Create `terraform/modules/vpc/outputs.tf`**

```hcl
output "vpc_id" {
  value = aws_vpc.main.id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "private_subnet_ids_csv" {
  value = join(",", aws_subnet.private[*].id)
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "lambda_sg_id" {
  value = aws_security_group.lambda.id
}

output "aurora_sg_id" {
  value = aws_security_group.aurora.id
}

output "redis_sg_id" {
  value = aws_security_group.redis.id
}
```

- [ ] **Step 4: Commit**

```bash
git add terraform/modules/vpc/
git commit -m "infra(terraform): vpc module — subnets, NAT GW, security groups"
```

---

### Task 4: Aurora Module

**Files:**
- Create: `terraform/modules/aurora/variables.tf`
- Create: `terraform/modules/aurora/main.tf`
- Create: `terraform/modules/aurora/outputs.tf`

- [ ] **Step 1: Create `terraform/modules/aurora/variables.tf`**

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
  default = 4 # FREE TIER cap. PRODUCTION UPGRADE: raise to 16+
}
```

- [ ] **Step 2: Create `terraform/modules/aurora/main.tf`**

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

# FREE TIER: RDS Proxy removed — not available on AWS free tier accounts.
#
# PRODUCTION UPGRADE: Re-add the following resources when moving to paid tier:
#
#   resource "aws_iam_role" "rds_proxy" { ... }           — allows RDS to read the DB secret
#   resource "aws_iam_role_policy" "rds_proxy_secrets" { ... }
#   resource "aws_db_proxy" "main" { ... }                — connection pool in front of Aurora
#   resource "aws_db_proxy_default_target_group" "main" { ... }
#   resource "aws_db_proxy_target" "main" { ... }
#
# Benefits unlocked: connection pooling (critical at >200 Lambda VUs), graceful Aurora
# pause/resume, transparent secret rotation.
# After adding: change DB_HOST env var on Lambda from cluster_endpoint → proxy endpoint,
# and update outputs.tf to expose aws_db_proxy.main.endpoint instead of cluster endpoint.
```

- [ ] **Step 3: Create `terraform/modules/aurora/outputs.tf`**

```hcl
# FREE TIER: exposes cluster endpoint directly (no proxy).
# PRODUCTION UPGRADE: replace value with aws_db_proxy.main.endpoint and rename to rds_proxy_endpoint.
output "cluster_endpoint" {
  value = aws_rds_cluster.main.endpoint
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

- [ ] **Step 4: Commit**

```bash
git add terraform/modules/aurora/
git commit -m "infra(terraform): aurora module — serverless v2, secrets manager (no proxy, free tier)"
```

---

### Task 5: Redis Module

**Files:**
- Create: `terraform/modules/redis/variables.tf`
- Create: `terraform/modules/redis/main.tf`
- Create: `terraform/modules/redis/outputs.tf`

- [ ] **Step 1: Create `terraform/modules/redis/variables.tf`**

```hcl
variable "name_prefix" {
  type    = string
  default = "newsletter"
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}
```

- [ ] **Step 2: Create `terraform/modules/redis/main.tf`**

```hcl
resource "aws_elasticache_serverless_cache" "main" {
  engine = "redis"
  name   = "${var.name_prefix}-redis"

  cache_usage_limits {
    data_storage {
      maximum = 10
      unit    = "GB"
    }
    ecpu_per_second {
      maximum = 5000
    }
  }

  subnet_ids         = var.subnet_ids
  security_group_ids = [var.security_group_id]
}
```

- [ ] **Step 3: Create `terraform/modules/redis/outputs.tf`**

```hcl
output "redis_endpoint" {
  value = tolist(aws_elasticache_serverless_cache.main.endpoint)[0].address
}

output "redis_port" {
  value = tolist(aws_elasticache_serverless_cache.main.endpoint)[0].port
}
```

- [ ] **Step 4: Commit**

```bash
git add terraform/modules/redis/
git commit -m "infra(terraform): redis module — elasticache serverless"
```

---

### Task 6: Dev Environment Root

**Files:**
- Create: `terraform/envs/dev/backend.tf`
- Create: `terraform/envs/dev/main.tf`
- Create: `terraform/envs/dev/variables.tf`
- Create: `terraform/envs/dev/outputs.tf`
- Create: `terraform/envs/dev/terraform.tfvars.example`

- [ ] **Step 1: Create `terraform/envs/dev/backend.tf`**

```hcl
terraform {
  backend "s3" {
    bucket         = "newsletter-tfstate-REPLACE_WITH_ACCOUNT_ID"
    key            = "dev/terraform.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "newsletter-tfstate-lock"
    encrypt        = true
  }
}
```

Note: Replace `REPLACE_WITH_ACCOUNT_ID` with the actual AWS account ID (from `terraform output account_id` in the bootstrap directory) before running `terraform init`. See Task 8.

- [ ] **Step 2: Create `terraform/envs/dev/main.tf`**

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

- [ ] **Step 3: Create `terraform/envs/dev/variables.tf`**

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

# FREE TIER: capped at 4 ACUs. PRODUCTION UPGRADE: raise to 16 (or higher).
variable "aurora_max_capacity" {
  type    = number
  default = 4
}
```

- [ ] **Step 4: Create `terraform/envs/dev/outputs.tf`**

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

# FREE TIER: direct cluster endpoint. PRODUCTION UPGRADE: swap to module.aurora.rds_proxy_endpoint.
output "cluster_endpoint" {
  value = module.aurora.cluster_endpoint
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

- [ ] **Step 5: Create `terraform/envs/dev/terraform.tfvars.example`**

```hcl
# Copy this to terraform.tfvars (gitignored) to override any defaults.
# All variables have sensible dev defaults in variables.tf.
# Only set values here if you need to override defaults.

# region              = "eu-west-1"
# name_prefix         = "newsletter-dev"
# aurora_min_capacity = 0.5
# aurora_max_capacity = 4   # free tier cap; raise to 16 for production
```

- [ ] **Step 6: Validate the full module graph**

```bash
cd terraform/envs/dev
terraform init -backend=false
terraform validate
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 7: Commit**

```bash
cd ../../..
git add terraform/envs/dev/
git commit -m "infra(terraform): dev environment root — wires vpc, aurora, redis modules"
```

---

### Task 7: Update SAM Template + Create deploy.sh

The SAM template currently creates its own `LambdaSG` resource. Lambda must use the Terraform-managed `lambda_sg` so that the Aurora and Redis security groups (which whitelist `lambda_sg`) allow the connections. This task removes `LambdaSG` from SAM and passes the Terraform-managed SG ID instead.

**Files:**
- Modify: `infra/template.yaml` (in `feat/api-serving-layer` worktree at `.worktrees/feat/api-serving-layer/infra/template.yaml`)
- Create: `scripts/deploy.sh`

- [ ] **Step 1: Add `LambdaSecurityGroupId` parameter to `infra/template.yaml`**

In `.worktrees/feat/api-serving-layer/infra/template.yaml`, add after the `RedisHost` parameter:

```yaml
  LambdaSecurityGroupId:
    Type: AWS::EC2::SecurityGroup::Id
    Description: Terraform-managed Lambda security group (allows egress to Aurora and Redis)
```

- [ ] **Step 2: Remove `LambdaSG` resource from `infra/template.yaml`**

Delete the entire `LambdaSG` resource block:

```yaml
  LambdaSG:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Lambda outbound to Aurora and Redis
      VpcId: !Ref VpcId
```

- [ ] **Step 3: Update VpcConfig reference in `infra/template.yaml`**

In `Globals.Function.VpcConfig`, change:

```yaml
    VpcConfig:
      SecurityGroupIds: [!Ref LambdaSG]
      SubnetIds: !Ref SubnetIds
```

to:

```yaml
    VpcConfig:
      SecurityGroupIds: [!Ref LambdaSecurityGroupId]
      SubnetIds: !Ref SubnetIds
```

- [ ] **Step 4: Validate the modified SAM template**

```bash
sam validate --template .worktrees/feat/api-serving-layer/infra/template.yaml --lint
```

Expected: `infra/template.yaml is a valid SAM Template`

- [ ] **Step 5: Commit the SAM template change**

```bash
cd .worktrees/feat/api-serving-layer
git add infra/template.yaml
git commit -m "infra(sam): use Terraform-managed Lambda SG via LambdaSecurityGroupId param"
cd ../../..
```

- [ ] **Step 6: Create `scripts/deploy.sh`**

```bash
#!/usr/bin/env bash
# Reads Terraform outputs from terraform/envs/dev and calls sam deploy.
# Run from project root: ./scripts/deploy.sh
set -euo pipefail

TF_DIR="terraform/envs/dev"
SAM_TEMPLATE="infra/template.yaml"
SAM_CONFIG="samconfig.toml"

echo "Reading Terraform outputs..."
VPC_ID=$(terraform -chdir="$TF_DIR" output -raw vpc_id)
SUBNET_IDS=$(terraform -chdir="$TF_DIR" output -raw private_subnet_ids_csv)
LAMBDA_SG=$(terraform -chdir="$TF_DIR" output -raw lambda_sg_id)
# FREE TIER: reads cluster_endpoint directly. PRODUCTION UPGRADE: change to rds_proxy_endpoint.
DB_HOST=$(terraform -chdir="$TF_DIR" output -raw cluster_endpoint)
REDIS_HOST=$(terraform -chdir="$TF_DIR" output -raw redis_endpoint)
DB_PASSWORD=$(terraform -chdir="$TF_DIR" output -raw db_password)
DB_NAME=$(terraform -chdir="$TF_DIR" output -raw db_name)
DB_USER=$(terraform -chdir="$TF_DIR" output -raw db_user)

echo "Deploying SAM stack..."
sam deploy \
  --template-file "$SAM_TEMPLATE" \
  --config-file "$SAM_CONFIG" \
  --no-confirm-changeset \
  --parameter-overrides \
    Environment=dev \
    VpcId="$VPC_ID" \
    SubnetIds="$SUBNET_IDS" \
    LambdaSecurityGroupId="$LAMBDA_SG" \
    DbHost="$DB_HOST" \
    RedisHost="$REDIS_HOST" \
    DbPassword="$DB_PASSWORD" \
    DbName="$DB_NAME" \
    DbUser="$DB_USER"

echo "Deploy complete."
```

- [ ] **Step 7: Make deploy.sh executable and commit**

```bash
chmod +x scripts/deploy.sh
git add scripts/deploy.sh
git commit -m "infra: deploy.sh reads TF outputs and calls sam deploy"
```

---

### Task 8: Execute Bootstrap and Provision Infrastructure

This task is manual execution — no code to write. Run from the project root.

- [ ] **Step 1: Run bootstrap (one-time)**

```bash
cd terraform/bootstrap
terraform init
terraform apply -auto-approve
```

Expected output ends with:
```
Outputs:

account_id = "123456789012"
lock_table = "newsletter-tfstate-lock"
state_bucket = "newsletter-tfstate-123456789012"
```

Note the `account_id` value.

- [ ] **Step 2: Fill account ID in backend.tf**

```bash
ACCOUNT_ID=$(terraform output -raw account_id)
cd ../envs/dev
sed -i "s/REPLACE_WITH_ACCOUNT_ID/$ACCOUNT_ID/" backend.tf
```

Verify `backend.tf` now contains the real account ID:

```bash
grep bucket backend.tf
```

Expected: `bucket = "newsletter-tfstate-123456789012"` (with your actual account ID)

- [ ] **Step 3: Commit the filled-in backend.tf**

```bash
cd ../../..
git add terraform/envs/dev/backend.tf
git commit -m "infra(terraform): set S3 backend bucket with account ID"
```

- [ ] **Step 4: Init dev environment with S3 backend**

```bash
cd terraform/envs/dev
terraform init
```

Expected: `Terraform has been successfully initialized!`

- [ ] **Step 5: Plan**

```bash
terraform plan
```

Expected: Plan shows ~25 resources to create, no errors.

- [ ] **Step 6: Apply (~10–15 min)**

```bash
terraform apply -auto-approve
```

Expected output ends with:
```
Apply complete! Resources: ~25 added, 0 changed, 0 destroyed.

Outputs:

db_name = "newsletter"
db_password = <sensitive>
db_user = "newsletter"
lambda_sg_id = "sg-..."
private_subnet_ids_csv = "subnet-...,subnet-..."
cluster_endpoint = "newsletter-dev-aurora.cluster-....eu-west-1.rds.amazonaws.com"
redis_endpoint = "newsletter-dev-redis.serverless.euw1.cache.amazonaws.com"
vpc_id = "vpc-..."
```

- [ ] **Step 7: Commit the Terraform lock file**

```bash
cd ../../..
git add terraform/envs/dev/.terraform.lock.hcl
git commit -m "chore(terraform): commit provider lock file for reproducible builds"
```

- [ ] **Step 8: Run SAM deploy**

```bash
./scripts/deploy.sh
```

Expected: SAM stack `newsletter-api-dev` created/updated. Output includes `ApiUrl`.

- [ ] **Step 9: Verify API Gateway routes**

```bash
API_URL=$(aws cloudformation describe-stacks \
  --stack-name newsletter-api-dev \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
  --output text)

echo "API URL: $API_URL"

# Unauthenticated call should return 401 (Cognito auth required)
curl -s -o /dev/null -w "%{http_code}" "$API_URL/newsletters"
```

Expected: `401` (confirms API Gateway + Cognito authorizer is wired up).

---

## Full Deployment Sequence (Reference)

After all tasks complete, the end-to-end flow is:

```bash
# 1. Bootstrap (once per account — already done after Task 8)
cd terraform/bootstrap && terraform apply

# 2. Provision infrastructure (Task 8)
cd terraform/envs/dev && terraform apply

# 3. Deploy Lambda + API Gateway
cd ../../.. && ./scripts/deploy.sh

# 4. Seed data into Aurora
DB_HOST=$(terraform -chdir=terraform/envs/dev output -raw cluster_endpoint)
DB_PASSWORD=$(terraform -chdir=terraform/envs/dev output -raw db_password)
DB_HOST=$DB_HOST DB_PASSWORD=$DB_PASSWORD python scripts/seed.py

# 5. Create Cognito test tokens
COGNITO_USER_POOL_ID=$(aws cloudformation describe-stacks \
  --stack-name newsletter-api-dev \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
  --output text)
COGNITO_CLIENT_ID=$(aws cloudformation describe-stacks \
  --stack-name newsletter-api-dev \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" \
  --output text)
COGNITO_USER_POOL_ID=$COGNITO_USER_POOL_ID \
COGNITO_CLIENT_ID=$COGNITO_CLIENT_ID \
  python scripts/create_test_tokens.py > tokens.txt

# 6. Run k6 load tests
export API_URL=<from CloudFormation output>
export COGNITO_TOKEN=$(head -1 tokens.txt)
k6 run -e API_URL=$API_URL -e COGNITO_TOKEN=$COGNITO_TOKEN load_tests/mixed_realistic.js
```

---

## Production Upgrade: Add RDS Proxy

When moving off free tier, add connection pooling via RDS Proxy. No app logic changes — only infra + one env var.

### Step 1: Restore proxy resources in `terraform/modules/aurora/main.tf`

Add after `aws_rds_cluster_instance.writer`:

```hcl
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

### Step 2: Update `terraform/modules/aurora/outputs.tf`

Replace `cluster_endpoint` output:

```hcl
output "rds_proxy_endpoint" {
  value = aws_db_proxy.main.endpoint
}
```

### Step 3: Update `terraform/envs/dev/outputs.tf`

```hcl
output "rds_proxy_endpoint" {
  value = module.aurora.rds_proxy_endpoint
}
```

### Step 4: Update `scripts/deploy.sh`

```bash
DB_HOST=$(terraform -chdir="$TF_DIR" output -raw rds_proxy_endpoint)
```

### Step 5: Raise Aurora capacity in `terraform/envs/dev/variables.tf`

```hcl
variable "aurora_max_capacity" {
  type    = number
  default = 16
}
```

### Step 6: Apply + redeploy

```bash
cd terraform/envs/dev && terraform apply
cd ../../.. && ./scripts/deploy.sh
```

Proxy creation takes ~5 min. After apply, `DB_HOST` Lambda env var automatically points to proxy endpoint.
