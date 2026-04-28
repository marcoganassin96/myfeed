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
