#!/usr/bin/env bash
# Provision (or reuse) a t3.micro EC2 k6 runner in eu-west-1.
# No SSH key pair — access via SSM Session Manager.
#
# Usage:
#   bash scripts/deploy_k6_runner.sh            # provision + sync load_tests/
#   bash scripts/deploy_k6_runner.sh --sync     # re-sync load_tests/ to existing instance
#   bash scripts/deploy_k6_runner.sh --destroy  # terminate instance
#
# Optional env vars:
#   AWS_DEFAULT_REGION  (default: eu-west-1)
#   EC2_INSTANCE_TYPE   (default: t3.micro)
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-eu-west-1}"
INSTANCE_TYPE="${EC2_INSTANCE_TYPE:-t3.micro}"
INSTANCE_NAME="newsletter-k6-runner"
SUBNET_ID="subnet-0f2f6a08dab6bc62b"    # eu-west-1a public subnet, same VPC as ALB
VPC_ID="vpc-0569eb1bb61f710a6"
ROLE_NAME="newsletter-k6-runner-role"
PROFILE_NAME="newsletter-k6-runner"
SG_NAME="newsletter-k6-runner-sg"
ALB_DNS="newsletter-dev-alb-1677270360.eu-west-1.elb.amazonaws.com"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOAD_TESTS_DIR="$ROOT_DIR/load_tests"

# ─── helpers ──────────────────────────────────────────────────────────────────

ssm_run() {
  local instance_id="$1"
  local desc="$2"
  local commands_json="$3"

  local cmd_id
  cmd_id=$(aws ssm send-command \
    --instance-ids "$instance_id" \
    --document-name "AWS-RunShellScript" \
    --parameters "{\"commands\":$commands_json}" \
    --region "$REGION" \
    --query "Command.CommandId" \
    --output text)

  local status="InProgress"
  for i in $(seq 1 36); do
    status=$(aws ssm get-command-invocation \
      --command-id "$cmd_id" \
      --instance-id "$instance_id" \
      --region "$REGION" \
      --query "Status" --output text 2>/dev/null || echo "InProgress")
    case "$status" in
      Success) echo "  ✓ $desc" >&2; return 0 ;;
      Failed|Cancelled|TimedOut)
        local err
        err=$(aws ssm get-command-invocation \
          --command-id "$cmd_id" --instance-id "$instance_id" \
          --region "$REGION" \
          --query "StandardErrorContent" --output text 2>/dev/null || true)
        echo "  ✗ $desc failed ($status): $err" >&2
        return 1 ;;
    esac
    sleep 5
  done
  echo "  ✗ $desc timed out after 3 min" >&2
  return 1
}

find_instance() {
  aws ec2 describe-instances \
    --filters \
      "Name=tag:Name,Values=$INSTANCE_NAME" \
      "Name=instance-state-name,Values=running,stopped,pending" \
    --query "Reservations[0].Instances[0].InstanceId" \
    --output text --region "$REGION"
}

# ─── destroy ──────────────────────────────────────────────────────────────────

if [[ "${1:-}" == "--destroy" ]]; then
  INSTANCE_ID=$(find_instance)
  if [[ "$INSTANCE_ID" == "None" || -z "$INSTANCE_ID" ]]; then
    echo "No instance named $INSTANCE_NAME found." >&2
  else
    aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" --region "$REGION" > /dev/null
    echo "Terminating $INSTANCE_ID" >&2
  fi
  exit 0
fi

# ─── locate existing instance ─────────────────────────────────────────────────

INSTANCE_ID=$(find_instance)

if [[ "${1:-}" == "--sync" ]]; then
  if [[ "$INSTANCE_ID" == "None" || -z "$INSTANCE_ID" ]]; then
    echo "ERROR: No instance found. Run without --sync to provision first." >&2
    exit 1
  fi
  echo "=== Sync-only mode: $INSTANCE_ID ===" >&2
else
  # ─── Step 1: Latest AL2023 AMI ──────────────────────────────────────────────
  echo "=== Resolving AMI ===" >&2
  AMI_ID=$(aws ec2 describe-images \
    --owners amazon \
    --filters \
      "Name=name,Values=al2023-ami-2023.*-x86_64" \
      "Name=state,Values=available" \
    --query "sort_by(Images, &CreationDate)[-1].ImageId" \
    --output text \
    --region "$REGION")
  echo "  AMI: $AMI_ID" >&2

  # ─── Step 2: IAM role + instance profile for SSM ────────────────────────────
  echo "=== Ensuring IAM ===" >&2
  if ! aws iam get-role --role-name "$ROLE_NAME" > /dev/null 2>&1; then
    aws iam create-role \
      --role-name "$ROLE_NAME" \
      --assume-role-policy-document \
        '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
      > /dev/null
    aws iam attach-role-policy \
      --role-name "$ROLE_NAME" \
      --policy-arn "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore" \
      > /dev/null
    echo "  Created role $ROLE_NAME" >&2
  else
    echo "  Role $ROLE_NAME exists" >&2
  fi

  if ! aws iam get-instance-profile --instance-profile-name "$PROFILE_NAME" > /dev/null 2>&1; then
    aws iam create-instance-profile --instance-profile-name "$PROFILE_NAME" > /dev/null
    aws iam add-role-to-instance-profile \
      --instance-profile-name "$PROFILE_NAME" \
      --role-name "$ROLE_NAME" \
      > /dev/null
    echo "  Created profile $PROFILE_NAME — waiting 15s for IAM propagation" >&2
    sleep 15
  else
    echo "  Profile $PROFILE_NAME exists" >&2
  fi

  # ─── Step 3: Security group (egress all, no inbound) ────────────────────────
  echo "=== Ensuring security group ===" >&2
  SG_ID=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
    --query "SecurityGroups[0].GroupId" \
    --output text --region "$REGION")

  if [[ "$SG_ID" == "None" || -z "$SG_ID" ]]; then
    SG_ID=$(aws ec2 create-security-group \
      --group-name "$SG_NAME" \
      --description "k6 runner: egress only, no inbound" \
      --vpc-id "$VPC_ID" \
      --region "$REGION" \
      --query "GroupId" --output text)
    echo "  Created SG $SG_ID" >&2
  else
    echo "  SG $SG_ID exists" >&2
  fi

  # ─── Step 4: Launch or start instance ───────────────────────────────────────
  if [[ "$INSTANCE_ID" == "None" || -z "$INSTANCE_ID" ]]; then
    echo "=== Launching EC2 ($INSTANCE_TYPE) ===" >&2
    INSTANCE_ID=$(aws ec2 run-instances \
      --image-id "$AMI_ID" \
      --instance-type "$INSTANCE_TYPE" \
      --subnet-id "$SUBNET_ID" \
      --security-group-ids "$SG_ID" \
      --iam-instance-profile "Name=$PROFILE_NAME" \
      --associate-public-ip-address \
      --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME}]" \
      --region "$REGION" \
      --query "Instances[0].InstanceId" \
      --output text)
    echo "  Launched $INSTANCE_ID" >&2
  else
    echo "=== Reusing instance $INSTANCE_ID ===" >&2
    STATE=$(aws ec2 describe-instances \
      --instance-ids "$INSTANCE_ID" \
      --query "Reservations[0].Instances[0].State.Name" \
      --output text --region "$REGION")
    if [[ "$STATE" == "stopped" ]]; then
      aws ec2 start-instances --instance-ids "$INSTANCE_ID" --region "$REGION" > /dev/null
      echo "  Starting stopped instance..." >&2
    fi
  fi

  # ─── Step 5: Wait for SSM online (up to 3 min) ──────────────────────────────
  echo "=== Waiting for SSM agent ===" >&2
  SSM_STATUS="Unknown"
  for i in $(seq 1 36); do
    SSM_STATUS=$(aws ssm describe-instance-information \
      --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
      --query "InstanceInformationList[0].PingStatus" \
      --output text --region "$REGION" 2>/dev/null || echo "Unknown")
    if [[ "$SSM_STATUS" == "Online" ]]; then
      echo "  SSM online." >&2
      break
    fi
    echo "  Attempt $i/36: $SSM_STATUS" >&2
    sleep 5
  done

  if [[ "$SSM_STATUS" != "Online" ]]; then
    echo "ERROR: SSM not online after 3 min. Check instance profile and VPC internet gateway." >&2
    exit 1
  fi

  # ─── Step 6: Install k6 ─────────────────────────────────────────────────────
  echo "=== Installing k6 ===" >&2
  ssm_run "$INSTANCE_ID" "install k6" \
    '["sudo dnf install -y https://dl.k6.io/rpm/repo.rpm 2>/dev/null || true","sudo dnf install -y k6","k6 version"]'
fi

# ─── Step 7: Sync load_tests/ and env files ──────────────────────────────────
echo "=== Syncing load_tests/ ===" >&2
ssm_run "$INSTANCE_ID" "mkdir load_tests" '["mkdir -p /tmp/load_tests && chmod 755 /tmp/load_tests"]'

for f in "$LOAD_TESTS_DIR"/*.js; do
  fname=$(basename "$f")
  b64=$(base64 -w0 "$f")
  ssm_run "$INSTANCE_ID" "upload $fname" \
    "[\"echo '$b64' | base64 -d > /tmp/load_tests/$fname && chmod 644 /tmp/load_tests/$fname\"]"
done

# ─── Done ─────────────────────────────────────────────────────────────────────
cat >&2 <<EOF

========================================
  k6 runner ready
  Instance: $INSTANCE_ID
========================================

Connect:
  aws ssm start-session --target $INSTANCE_ID --region $REGION

Run a test (on the EC2 instance):

  export COGNITO_TOKEN=...
  export NEWSLETTER_IDS=...

  k6 run  --env API_URL=http://$ALB_DNS --env COGNITO_TOKEN=\$COGNITO_TOKEN  --env NEWSLETTER_IDS=\$NEWSLETTER_IDS /tmp/load_tests/newsletter_uncached.js
Re-sync load_tests/ + env after local edits or token refresh:
  bash scripts/deploy_k6_runner.sh --sync

Destroy when done (stops billing):
  bash scripts/deploy_k6_runner.sh --destroy

EOF
