variable "name_prefix" {
  type    = string
  default = "newsletter-mdg"
  validation {
    condition     = length(var.name_prefix) <= 18
    error_message = "name_prefix must be 18 chars or fewer (ALB name = name_prefix + '-internal-alb' must not exceed 32 chars)."
  }
}

variable "vpc_id" {
  type        = string
  description = "VPC ID for internal ALB and security group placement"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for internal ALB and ECS tasks"
}

variable "aurora_sg_id" {
  type        = string
  description = "Existing aurora SG — module adds ingress rule 5432 from MDG fargate SG"
}

variable "redis_sg_id" {
  type        = string
  description = "Existing redis SG — module adds ingress rule 6379 from MDG fargate SG"
}

variable "newsletter_fargate_sg_id" {
  type        = string
  description = "Newsletter fargate SG — internal ALB allows ingress 80 from it"
}

variable "db_host" {
  type        = string
  description = "DB hostname. Free tier: module.aurora.cluster_endpoint. Premium: module.aurora.rds_proxy_endpoint."
}

variable "db_name" {
  type        = string
  default     = "newsletter"
  description = "PostgreSQL database name"
}

variable "db_user" {
  type    = string
  default = "newsletter"
}

variable "db_password" {
  type        = string
  sensitive   = true
  description = "DB password — stored in Secrets Manager, not passed directly to container"
}

variable "redis_endpoint" {
  type        = string
  description = "Redis endpoint hostname (e.g. from module.redis.redis_endpoint)"
}

variable "region" {
  type    = string
  default = "eu-west-1"
}

variable "image_tag" {
  type        = string
  default     = "latest"
  description = "ECR image tag to deploy"
}
