#!/usr/bin/env bash
# Reads Terraform outputs from terraform/envs/dev and calls sam deploy.
# Run from project root: ./scripts/deploy.sh
set -euo pipefail

TF_DIR="terraform/envs/dev"
SAM_TEMPLATE="infra/template.yaml"
SAM_CONFIG="samconfig.toml"

echo "Reading Terraform outputs..."
VPC_ID=$(terraform -chdir="$TF_DIR" output -raw vpc_id)
SUBNET_IDS=$(terraform -chdir="$TF_DIR" output -raw private_subnet_ids_csv)
LAMBDA_SG=$(terraform -chdir="$TF_DIR" output -raw lambda_sg_id)
DB_HOST=$(terraform -chdir="$TF_DIR" output -raw rds_proxy_endpoint)
REDIS_HOST=$(terraform -chdir="$TF_DIR" output -raw redis_endpoint)
DB_PASSWORD=$(terraform -chdir="$TF_DIR" output -raw db_password)
DB_NAME=$(terraform -chdir="$TF_DIR" output -raw db_name)
DB_USER=$(terraform -chdir="$TF_DIR" output -raw db_user)

echo "Deploying SAM stack..."
sam deploy \
  --template-file "$SAM_TEMPLATE" \
  --config-file "$SAM_CONFIG" \
  --no-confirm-changeset \
  --parameter-overrides \
    Environment=dev \
    VpcId="$VPC_ID" \
    SubnetIds="$SUBNET_IDS" \
    LambdaSecurityGroupId="$LAMBDA_SG" \
    DbHost="$DB_HOST" \
    RedisHost="$REDIS_HOST" \
    DbPassword="$DB_PASSWORD" \
    DbName="$DB_NAME" \
    DbUser="$DB_USER"

echo "Deploy complete."
