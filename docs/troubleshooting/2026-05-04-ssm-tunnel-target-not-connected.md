# Troubleshooting: SSM Tunnel TargetNotConnected — Dev Bastion → RDS

**Date:** 2026-05-04
**Environment:** `newsletter-api-dev`, region `eu-west-1`
**Status:** Open

---

## Symptom

Cannot establish SSM Session Manager tunnel to bastion instance to reach the dev RDS instance.

```
An error occurred (TargetNotConnected) when calling the StartSession operation:
i-0bf6bb934b0aa0618 is not connected
```

This blocks local → RDS connectivity for dev testing (running `seed.py`, running migrations, psql inspection).

---

## Infrastructure State

| Resource | ID / Value |
|---|---|
| Bastion instance | `i-0bf6bb934b0aa0618` |
| Bastion public IP | `34.242.141.121` |
| Bastion security group | `sg-0d66b751fe22a2dd2` |
| IAM role | `newsletter-dev-bastion-ssm-role` |
| IAM managed policy | `AmazonSSMManagedInstanceCore` ✅ |
| VPC endpoints for SSM | **None** (only ElastiCache endpoints visible) |

---

## Network Path — Verified Correct

Terraform source (`terraform/modules/bastion/main.tf` + `terraform/envs/dev/main.tf`) confirms:

| Check | Status |
|---|---|
| Bastion subnet | `module.vpc.public_subnet_ids[0]` — **public subnet** ✅ |
| Public subnet route table | `0.0.0.0/0 → igw-*` ✅ |
| IGW exists | `aws_internet_gateway.main` ✅ |
| Bastion SG egress TCP 443 | `cidr_blocks = ["0.0.0.0/0"]` ✅ |
| IAM instance profile | `AmazonSSMManagedInstanceCore` attached ✅ |
| `associate_public_ip_address` | `true` ✅ |

**The absence of SSM VPC endpoints is not the issue.** VPC endpoints are only needed for private subnets with no NAT. This instance is in a public subnet with a working IGW — SSM traffic exits via the internet gateway. No VPC endpoints required.

## Root Cause Analysis

All prerequisites are correctly configured. `TargetNotConnected` with a healthy network path points to the **SSM agent** on the instance itself.

SSM agent requires outbound HTTPS (TCP 443) to three endpoints:

| Endpoint | Purpose |
|---|---|
| `ssm.eu-west-1.amazonaws.com` | Session control |
| `ec2messages.eu-west-1.amazonaws.com` | EC2 message relay |
| `ssmmessages.eu-west-1.amazonaws.com` | WebSocket session channel |

Terraform applied from `feat/api-serving-layer` worktree ✅ — IAM instance profile and SG confirmed correctly provisioned.

Likely causes (network + IAM ruled out):

1. **SSM agent did not start** — `user_data` ran `systemctl restart amazon-ssm-agent` but may have failed silently (AL2023 agent is pre-installed; a restart race during boot is possible).
2. **SSM agent crashed** after start — check system log.

---

## Checks to Run

### 1. Verify instance appears in SSM Fleet Manager (fastest check)
- Systems Manager → Fleet Manager (eu-west-1)
- If `i-0bf6bb934b0aa0618` is absent: SSM agent is not connecting at all → see Check 3
- If present with "Connection Lost": agent was connected but dropped → restart agent

### 2. Check SSM agent logs via EC2 system log
- EC2 → instance → **Actions → Monitor and troubleshoot → Get system log**
- Look for lines containing `amazon-ssm-agent` — errors or absence of startup confirms agent issue

---

## Fix Options

### Option A — Restart SSM agent (if instance profile is attached)
Stop and start the instance (not reboot — stop/start forces new user_data run is NOT automatic, but SSM agent restarts):

```bash
aws ec2 stop-instances --region eu-west-1 --instance-ids i-0bf6bb934b0aa0618
aws ec2 start-instances --region eu-west-1 --instance-ids i-0bf6bb934b0aa0618
```

Or if you have shell access, connect via EC2 Instance Connect (see Workaround below) and run:
```bash
sudo systemctl restart amazon-ssm-agent
sudo systemctl status amazon-ssm-agent
```

### Option B — Replace instance (if user_data never ran correctly)
Terraform `taint` the bastion instance and re-apply from the worktree:

```bash
cd .worktrees/feat/api-serving-layer/terraform/envs/dev
terraform taint module.bastion.aws_instance.bastion
terraform apply
```

### Option C — Replace instance via Terraform (nuclear option)
If stop/start and manual restart both fail:

```bash
cd .worktrees/feat/api-serving-layer/terraform/envs/dev
terraform taint module.bastion.aws_instance.bastion
terraform apply
```

New instance will run `user_data` fresh on first boot.

---

## Workaround (while blocked)

Use EC2 Instance Connect if the instance is in a public subnet and port 22 is open:
```bash
aws ec2-instance-connect send-ssh-public-key \
  --region eu-west-1 \
  --instance-id i-0bf6bb934b0aa0618 \
  --availability-zone eu-west-1a \
  --instance-os-user ec2-user \
  --ssh-public-key file://~/.ssh/id_rsa.pub

ssh -i ~/.ssh/id_rsa ec2-user@34.242.141.121
```
Then forward RDS port from inside the bastion shell.

---

## Resolution

**Status: Resolved 2026-05-04**

### Root causes

1. **SSM agent not installed** — the `al2023-ami-*-x86_64` AMI filter selects a minimal AL2023 image that does NOT include `amazon-ssm-agent`. The original `user_data` assumed it was pre-installed and only ran `systemctl restart`, which silently failed.

2. **Session Manager Plugin missing locally** — `aws ssm start-session` requires the [Session Manager Plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html) installed on the local machine separately from the AWS CLI. Error: `SessionManagerPlugin is not found`.

### Fixes applied

**Instance (immediate):** SSHed in via EC2 Instance Connect + direct key injection, then:
```bash
sudo dnf install -y amazon-ssm-agent
sudo systemctl enable amazon-ssm-agent
sudo systemctl start amazon-ssm-agent
```

**Terraform (permanent):** Updated `terraform/modules/bastion/main.tf` `user_data` to install SSM agent on first boot:
```bash
dnf install -y amazon-ssm-agent
systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent
```

**Local machine:** Installed Session Manager Plugin via `SessionManagerPluginSetup.exe`.

### Verification
```
aws ssm start-session --region eu-west-1 --target i-01aca106a1c356f0c
Starting session with SessionId: marco-admin-a22ptn5jrpnjgtlviapsqorzo8
```
