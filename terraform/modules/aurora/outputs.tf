# FREE TIER: RDS PostgreSQL db.t3.micro instance address.
# PRODUCTION UPGRADE: replace value with aws_rds_cluster.main.endpoint (Aurora) or aws_db_proxy.main.endpoint (with proxy).
output "cluster_endpoint" {
  value = aws_db_instance.main.address
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
