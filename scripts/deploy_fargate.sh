#!/usr/bin/env bash
# Build Docker image, push to ECR, force ECS service redeployment.
# Required env vars: ECR_REPO_URL, ECS_CLUSTER, ECS_SERVICE
# Optional: AWS_DEFAULT_REGION (default: eu-west-1)
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-eu-west-1}"
REPO="${ECR_REPO_URL:?ECR_REPO_URL is required}"
CLUSTER="${ECS_CLUSTER:?ECS_CLUSTER is required}"
SERVICE="${ECS_SERVICE:?ECS_SERVICE is required}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== ECR login ===" >&2
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${REPO%%/*}"

echo "=== docker build ===" >&2
docker build -t newsletter:latest "$ROOT_DIR"

echo "=== docker tag + push ===" >&2
docker tag newsletter:latest "$REPO:latest"
docker push "$REPO:latest"

echo "=== force ECS redeployment ===" >&2
aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --force-new-deployment \
  --region "$REGION" \
  --output json > /dev/null

echo "Deploy triggered. Tasks will cycle with new image." >&2
