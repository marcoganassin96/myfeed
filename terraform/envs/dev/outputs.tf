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

output "bastion_instance_id" {
  value       = module.bastion.instance_id
  description = "SSM target for RDS port forwarding"
}

output "alb_dns" {
  value = module.fargate.alb_dns
}

output "ecr_repo_url" {
  value = module.fargate.ecr_repo_url
}

output "ecs_cluster" {
  value = module.fargate.cluster_name
}

output "ecs_service" {
  value = module.fargate.service_name
}
