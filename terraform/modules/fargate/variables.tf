variable "name_prefix" {
  type    = string
  default = "newsletter"
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "aurora_sg_id" {
  type        = string
  description = "Existing aurora SG — fargate module adds an ingress rule to it"
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

variable "cognito_user_pool_id" {
  type        = string
  description = "SAM-managed Cognito User Pool ID for JWT verification"
}

variable "cognito_client_id" {
  type        = string
  description = "Cognito app client ID for JWT audience validation"
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

variable "allow_cache_bypass" {
  type    = string
  default = "false"
}

variable "app_env" {
  type        = string
  default     = "dev"
  description = "Value for the 'env' env var — controls which config YAML is loaded (local/dev/prd)"
}
