#!/usr/bin/env bash
# Reads Terraform outputs and deploys the SAM stack.
# Usage: ./scripts/deploy.sh [ENV]   (default: dev)
# Example: ./scripts/deploy.sh prod
set -euo pipefail

ENV="${1:-dev}"

if command -v sam &>/dev/null; then
  SAM=sam
elif command -v sam.cmd &>/dev/null; then
  SAM=sam.cmd
else
  echo "Error: AWS SAM CLI not found. Install: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html" >&2
  exit 1
fi

TF_DIR="terraform/envs/${ENV}"
SAM_TEMPLATE="infra/template.yaml"
SAM_BUILD_TEMPLATE=".aws-sam/build/template.yaml"

echo "Reading Terraform outputs (env: ${ENV})..."
VPC_ID=$(terraform -chdir="$TF_DIR" output -raw vpc_id)
SUBNET_IDS=$(terraform -chdir="$TF_DIR" output -raw private_subnet_ids_csv)
LAMBDA_SG=$(terraform -chdir="$TF_DIR" output -raw lambda_sg_id)
DB_HOST=$(terraform -chdir="$TF_DIR" output -raw cluster_endpoint)
REDIS_HOST=$(terraform -chdir="$TF_DIR" output -raw redis_endpoint)
DB_PASSWORD=$(terraform -chdir="$TF_DIR" output -raw db_password)
DB_NAME=$(terraform -chdir="$TF_DIR" output -raw db_name)
DB_USER=$(terraform -chdir="$TF_DIR" output -raw db_user)

echo "Building SAM stack..."
"$SAM" build --template-file "$SAM_TEMPLATE"

echo "Deploying SAM stack..."
"$SAM" deploy \
  --template-file "$SAM_BUILD_TEMPLATE" \
  --stack-name "newsletter-api-${ENV}" \
  --no-confirm-changeset \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    Environment="${ENV}" \
    VpcId="$VPC_ID" \
    SubnetIds="$SUBNET_IDS" \
    LambdaSecurityGroupId="$LAMBDA_SG" \
    DbHost="$DB_HOST" \
    RedisHost="$REDIS_HOST" \
    DbPassword="$DB_PASSWORD" \
    DbName="$DB_NAME" \
    DbUser="$DB_USER"

echo "Deploy complete."
