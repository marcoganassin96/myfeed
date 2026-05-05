# How to Connect to RDS (Dev) via SSM Tunnel

Access the private RDS PostgreSQL instance from your local machine through the SSM bastion.

## Prerequisites

- AWS CLI configured with dev account credentials (`eu-west-1`)
- [Session Manager Plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html) installed
- `psql` installed locally
- Bastion instance running (check EC2 console or `terraform output` in `terraform/envs/dev`)

## Steps

### 1 — Open SSM port-forward tunnel (Terminal 1)

```cmd
aws ssm start-session --region eu-west-1 --target i-01aca106a1c356f0c --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters "{\"host\":[\"newsletter-dev-postgres.cjyo8yc62lie.eu-west-1.rds.amazonaws.com\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5432\"]}"
```

Keep this terminal open. Tunnel stays alive until Ctrl+C.

### 2 — Connect psql (Terminal 2)

```bash
psql -h localhost -U newsletter -d newsletter -p 5432
```

Password is in AWS Secrets Manager: `newsletter-dev-postgres-password` (eu-west-1).

## Reference values (dev)

| Resource | Value |
|---|---|
| Bastion instance ID | `i-01aca106a1c356f0c` |
| RDS hostname | `newsletter-dev-postgres.cjyo8yc62lie.eu-west-1.rds.amazonaws.com` |
| DB name | `newsletter` |
| DB user | `newsletter` |
| Local port | `5432` |

## Bash one-liner (Git Bash / WSL)

```bash
aws ssm start-session --region eu-west-1 --target i-01aca106a1c356f0c --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters '{"host":["newsletter-dev-postgres.cjyo8yc62lie.eu-west-1.rds.amazonaws.com"],"portNumber":["5432"],"localPortNumber":["5432"]}'
```

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `TargetNotConnected` | Bastion stopped or SSM agent down | Start instance; if new, wait 3 min after running state |
| `SessionManagerPlugin is not found` | Plugin not installed locally | Install Session Manager Plugin |
| `Connection timed out` on psql | Tunnel not open | Ensure Terminal 1 shows `Waiting for connections...` before running psql |
| `password authentication failed` | Wrong password | Fetch from Secrets Manager |
