terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.region
}

module "vpc" {
  source               = "../../modules/vpc"
  name_prefix          = var.name_prefix
  vpc_cidr             = var.vpc_cidr
  azs                  = var.azs
  private_subnet_cidrs = var.private_subnet_cidrs
  public_subnet_cidrs  = var.public_subnet_cidrs
}

module "aurora" {
  source            = "../../modules/aurora"
  name_prefix       = var.name_prefix
  vpc_id            = module.vpc.vpc_id
  subnet_ids        = module.vpc.private_subnet_ids
  security_group_id = module.vpc.aurora_sg_id
  db_name           = var.db_name
  db_user           = var.db_user
}

module "bastion" {
  source       = "../../modules/bastion"
  name_prefix  = var.name_prefix
  vpc_id       = module.vpc.vpc_id
  subnet_id    = module.vpc.public_subnet_ids[0]
  aurora_sg_id = module.vpc.aurora_sg_id
}

module "fargate" {
  source             = "../../modules/fargate"
  name_prefix        = var.name_prefix
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  aurora_sg_id         = module.vpc.aurora_sg_id
  aurora_secret_arn    = module.aurora.secret_arn
  db_host              = module.aurora.cluster_endpoint
  db_name              = var.db_name
  db_user              = var.db_user
  cognito_user_pool_id = var.cognito_user_pool_id
  cognito_client_id    = var.cognito_client_id
  region               = var.region
  uvicorn_workers      = var.fargate_uvicorn_workers
  allow_cache_bypass   = "true"
}

module "fargate_mdg" {
  source                   = "../../modules/fargate-mdg"
  name_prefix              = "${var.name_prefix}-mdg"
  vpc_id                   = module.vpc.vpc_id
  private_subnet_ids       = module.vpc.private_subnet_ids
  aurora_sg_id       = module.vpc.aurora_sg_id
  db_host            = module.aurora.cluster_endpoint
  db_name                  = var.db_name
  db_user                  = var.db_user
  db_password              = module.aurora.db_password
  region                   = var.region
  app_env                  = "dev"
}

