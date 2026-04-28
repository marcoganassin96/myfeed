variable "name_prefix" {
  type    = string
  default = "newsletter"
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
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

variable "min_capacity" {
  type    = number
  default = 0.5
}

variable "max_capacity" {
  type    = number
  default = 16
}
