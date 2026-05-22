#!/usr/bin/env bash
# Build MDG Docker image, push to ECR, force ECS service redeployment.
# Required env vars: MDG_ECR_REPO_URL, MDG_ECS_CLUSTER, MDG_ECS_SERVICE
# Optional: AWS_DEFAULT_REGION (default: eu-west-1)
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-eu-west-1}"
REPO="${MDG_ECR_REPO_URL:?MDG_ECR_REPO_URL is required}"
CLUSTER="${MDG_ECS_CLUSTER:?MDG_ECS_CLUSTER is required}"
SERVICE="${MDG_ECS_SERVICE:?MDG_ECS_SERVICE is required}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== ECR login ===" >&2
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${REPO%%/*}"

echo "=== docker build ===" >&2
docker build -f "$ROOT_DIR/mdg/Dockerfile" -t mdg:latest "$ROOT_DIR/mdg"

echo "=== docker tag + push ===" >&2
docker tag mdg:latest "$REPO:latest"
docker push "$REPO:latest"

echo "=== force ECS redeployment (latest task definition) ===" >&2
LATEST_TASK_DEF=$(aws ecs describe-task-definition \
  --task-definition "${SERVICE%-svc}" \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text \
  --region "$REGION")
echo "Task definition: $LATEST_TASK_DEF" >&2
aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --task-definition "$LATEST_TASK_DEF" \
  --force-new-deployment \
  --region "$REGION" \
  --output json > /dev/null

echo "Deploy triggered. Tasks will cycle with new image + task definition." >&2
