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
