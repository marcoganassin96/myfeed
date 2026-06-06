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

