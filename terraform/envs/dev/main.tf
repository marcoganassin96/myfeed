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

module "redis" {
  source            = "../../modules/redis"
  name_prefix       = var.name_prefix
  subnet_ids        = module.vpc.private_subnet_ids
  security_group_id = module.vpc.redis_sg_id
}

module "bastion" {
  source       = "../../modules/bastion"
  name_prefix  = var.name_prefix
  vpc_id       = module.vpc.vpc_id
  subnet_id    = module.vpc.public_subnet_ids[0]
  aurora_sg_id = module.vpc.aurora_sg_id
  redis_sg_id  = module.vpc.redis_sg_id
}

module "fargate" {
  source               = "../../modules/fargate"
  name_prefix          = var.name_prefix
  vpc_id               = module.vpc.vpc_id
  public_subnet_ids    = module.vpc.public_subnet_ids
  private_subnet_ids   = module.vpc.private_subnet_ids
  aurora_sg_id         = module.vpc.aurora_sg_id
  redis_sg_id          = module.vpc.redis_sg_id
  aurora_secret_arn    = module.aurora.secret_arn
  db_host              = module.aurora.cluster_endpoint
  db_name              = var.db_name
  db_user              = var.db_user
  redis_endpoint       = module.redis.redis_endpoint
  cognito_user_pool_id = var.cognito_user_pool_id
  region               = var.region
  uvicorn_workers      = var.fargate_uvicorn_workers
}
