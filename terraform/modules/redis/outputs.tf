output "redis_endpoint" {
  value = tolist(aws_elasticache_serverless_cache.main.endpoint)[0].address
}

output "redis_port" {
  value = tolist(aws_elasticache_serverless_cache.main.endpoint)[0].port
}
