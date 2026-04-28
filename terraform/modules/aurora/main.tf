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

# FREE TIER: Aurora Serverless v2 requires WithExpressConfiguration on free-tier accounts,
# unsupported by Terraform aws provider. Using RDS PostgreSQL db.t3.micro instead (free tier: 750h/month).
# PRODUCTION UPGRADE: replace aws_db_instance with aws_rds_cluster + aws_rds_cluster_instance
# (engine=aurora-postgresql, engine_mode=provisioned, serverlessv2_scaling_configuration).
resource "aws_db_instance" "main" {
  identifier        = "${var.name_prefix}-postgres"
  engine            = "postgres"
  engine_version    = "15.4"
  instance_class    = "db.t3.micro"
  allocated_storage = 20

  db_name  = var.db_name
  username = var.db_user
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.security_group_id]
  skip_final_snapshot    = true
  deletion_protection    = false
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
