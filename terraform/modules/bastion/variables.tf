variable "name_prefix" {
  type    = string
  default = "newsletter"
}

variable "vpc_id" {
  type = string
}

variable "subnet_id" {
  type        = string
  description = "Public subnet — instance needs internet access for SSM agent"
}

variable "aurora_sg_id" {
  type        = string
  description = "Aurora security group — bastion adds ingress rule 5432 to this SG"
}

variable "redis_sg_id" {
  type        = string
  description = "Redis security group — bastion adds ingress rule 6379 to this SG"
}
