variable "region" {
  type    = string
  default = "eu-west-1"
}

variable "name_prefix" {
  type    = string
  default = "newsletter-dev"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "azs" {
  type    = list(string)
  default = ["eu-west-1a", "eu-west-1b"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.101.0/24", "10.0.102.0/24"]
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
  description = "SAM-managed Cognito User Pool ID (from aws cognito-idp list-user-pools)"
}

variable "cognito_client_id" {
  type        = string
  description = "Cognito app client ID for JWT audience validation"
}

variable "fargate_uvicorn_workers" {
  type        = number
  default     = 1
  description = "Uvicorn workers per task. Free tier: 1. Premium (Aurora+Proxy): 3."
}

# PRODUCTION UPGRADE: restore aurora_min_capacity and aurora_max_capacity when switching to Aurora Serverless v2.
