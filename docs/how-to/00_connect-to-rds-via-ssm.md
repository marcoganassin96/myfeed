# How to Connect to RDS (Dev) via SSM Tunnel

Access the private RDS PostgreSQL instance from your local machine through the SSM bastion.

## Prerequisites

- AWS CLI configured with dev account credentials (`eu-west-1`)
- Session Manager Plugin installed locally — required by `aws ssm start-session`:
  ```powershell
  Invoke-WebRequest "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/windows/SessionManagerPluginSetup.exe" -OutFile "$env:TEMP\SessionManagerPluginSetup.exe"
  Start-Process -FilePath "$env:TEMP\SessionManagerPluginSetup.exe" -Wait
  ```
- `psql` installed locally
- Bastion instance **running** (see below)

## Start / stop the bastion

The bastion costs ~$8/month if left running. Stop it when not in use.

```bash
# get bastion instance ID
BASTION_ID=$(terraform -chdir=terraform/envs/dev output -raw bastion_instance_id)

# start before tunneling
aws ec2 start-instances --region eu-west-1 --instance-ids $BASTION_ID

# wait ~3 min after "running" state for SSM agent to register

# stop after use
aws ec2 stop-instances --region eu-west-1 --instance-ids $BASTION_ID
```

## Steps

### 1 — Open SSM port-forward tunnel (Terminal 1)

**PowerShell / cmd:**
```cmd
aws ssm start-session --region eu-west-1 --target i-01aca106a1c356f0c --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters "{\"host\":[\"newsletter-dev-postgres.cjyo8yc62lie.eu-west-1.rds.amazonaws.com\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5433\"]}"
```

**Git Bash / WSL (dynamic — reads IDs from Terraform output):**
```bash
BASTION_ID=$(terraform -chdir=terraform/envs/dev output -raw bastion_instance_id)
DB_HOST=$(terraform -chdir=terraform/envs/dev output -raw db_endpoint)

aws ssm start-session \
  --region eu-west-1 \
  --target "$BASTION_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"$DB_HOST\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5433\"]}"
```

Wait for `Waiting for connections...` before proceeding. Keep this terminal open — Ctrl+C closes the tunnel.

> **Port note:** local port `5433` avoids conflict if PostgreSQL is already running locally on `5432`.

### 2 — Connect psql (Terminal 2)

```bash
psql -h localhost -U newsletter -d newsletter -p 5433
```

Password is in AWS Secrets Manager: `newsletter-dev-postgres-password` (eu-west-1).

## Reference values (dev)

| Resource | Value |
|---|---|
| Bastion instance ID | `i-01aca106a1c356f0c` |
| RDS hostname | `newsletter-dev-postgres.cjyo8yc62lie.eu-west-1.rds.amazonaws.com` |
| DB name | `newsletter` |
| DB user | `newsletter` |
| Local tunnel port | `5433` |

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `TargetNotConnected` | Bastion stopped or SSM agent not ready | Start instance; wait 3 min after "running" state before retrying |
| `TargetNotConnected` on fresh instance | `amazon-ssm-agent` absent — AL2023 minimal AMI does not bundle it | `user_data` in bastion module installs it via `dnf`; taint + `terraform apply` if running pre-fix instance |
| `SessionManagerPlugin is not found` | Plugin not installed locally | Install Session Manager Plugin (see Prerequisites) |
| `Connection timed out` on psql | Tunnel not open | Confirm Terminal 1 shows `Waiting for connections...` |
| `password authentication failed` | Wrong password | Fetch from Secrets Manager |
