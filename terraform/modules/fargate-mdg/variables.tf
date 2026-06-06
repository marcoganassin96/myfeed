variable "name_prefix" {
  type    = string
  default = "newsletter-mdg"
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for ECS tasks"
}

variable "aurora_sg_id" {
  type        = string
  description = "Existing aurora SG — module adds ingress rule 5432 from MDG fargate SG"
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

variable "region" {
  type    = string
  default = "eu-west-1"
}

variable "image_tag" {
  type        = string
  default     = "latest"
  description = "ECR image tag to deploy"
}

variable "app_env" {
  type        = string
  default     = "prod"
  description = "APP_ENV passed to the container (e.g. dev, prod)"
}
