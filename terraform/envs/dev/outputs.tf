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
