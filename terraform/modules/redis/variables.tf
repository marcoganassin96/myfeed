variable "name_prefix" {
  type    = string
  default = "newsletter"
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}
