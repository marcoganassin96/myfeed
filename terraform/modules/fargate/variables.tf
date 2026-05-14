variable "name_prefix" {
  type    = string
  default = "newsletter"
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "aurora_sg_id" {
  type        = string
  description = "Existing aurora SG — fargate module adds an ingress rule to it"
}

variable "redis_sg_id" {
  type        = string
  description = "Existing redis SG — fargate module adds an ingress rule to it"
}

variable "aurora_secret_arn" {
  type        = string
  description = "Secrets Manager ARN for DB password (injected into container)"
}

variable "db_host" {
  type = string
}

variable "db_name" {
  type    = string
  default = "newsletter"
}

variable "db_user" {
  type    = string
  default = "newsletter"
}

variable "redis_endpoint" {
  type = string
}

variable "cognito_user_pool_id" {
  type        = string
  description = "SAM-managed Cognito User Pool ID for JWT verification"
}

variable "region" {
  type    = string
  default = "eu-west-1"
}

variable "uvicorn_workers" {
  type        = number
  default     = 1
  description = "Uvicorn worker count. Free tier: 1 (max 40 DB conns). Premium (Aurora+Proxy): 3."
}

variable "image_tag" {
  type    = string
  default = "latest"
}
