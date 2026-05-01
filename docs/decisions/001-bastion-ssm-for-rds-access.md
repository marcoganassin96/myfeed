# ADR-001: EC2 Bastion with SSM for RDS Access

**Date:** 2026-05-01  
**Status:** Accepted  
**Author:** Marco Ganassin

---

## Context

RDS PostgreSQL is in a private VPC subnet. Access from outside the VPC is blocked by design — the aurora security group only allows inbound on port 5432 from the Lambda security group.

Two operational tasks require direct DB access from a developer workstation:

1. Running `scripts/seed.py` to populate mock data before load tests
2. Running `scripts/01_get_load_test_ids.py` to extract newsletter and event UUIDs for k6

---

## Options Considered

### Option 1 — Temporary Security Group Rule (local machine → RDS)

Temporarily add the developer's public IP to the aurora security group on port 5432, run the scripts locally, then revoke the rule.

**Rejected because:**

- **Load test skew (bandwidth & latency):** k6 load tests run from local machine saturate the local internet uplink. Network bottlenecks on the client side become the bottleneck, not the API under test. Results (p99, p95 latency, error rates) are invalid. k6 must run from within AWS or from a machine with a stable, high-bandwidth connection close to the API.
- **Security group hygiene:** Opening the aurora SG to a residential/office IP, even temporarily, is error-prone. The rule can be forgotten. It exposes the DB to the public internet (the developer's current IP may change or be shared on a NAT).
- **Not automatable:** The IP must be looked up and injected manually each session. Cannot be scripted safely.

### Option 2 — EC2 Bastion with SSM Port Forwarding (chosen)

Deploy a `t3.micro` Amazon Linux 2023 instance in a public subnet. Use AWS SSM Session Manager to create an encrypted tunnel from the developer workstation to the bastion, then forward port 5432 from the bastion to the RDS endpoint.

**Chosen because:**

- **No public DB exposure:** RDS aurora SG only allows 5432 from the bastion security group. No residential IP involved.
- **No SSH keys:** SSM uses IAM authentication. No key pairs to manage or rotate.
- **k6 runs from EC2 (future):** The bastion (or a separate load generator EC2 in the same VPC) can run k6 directly inside AWS. Traffic from k6 → API Gateway stays within the AWS network. Results reflect real latency without local uplink interference.
- **Auditable:** SSM session activity is logged to CloudTrail. Temporary SG rules are not.
- **Automatable:** `aws ssm start-session` is a single CLI command. Can be scripted into the pipeline.

---

## Decision

Deploy `terraform/modules/bastion` — `t3.micro` AL2023 in public subnet with `AmazonSSMManagedInstanceCore` IAM policy. The bastion module owns the `aws_security_group_rule` that adds ingress 5432 → aurora SG, keeping the VPC module unchanged.

Exposes `bastion_instance_id` as a Terraform output for use in SSM commands.

---

## Usage

```bash
# 1. get bastion ID
BASTION_ID=$(terraform -chdir=terraform/envs/dev output -raw bastion_instance_id)

# 2. open tunnel (keep this terminal open)
aws ssm start-session \
  --target $BASTION_ID \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"$DB_HOST\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5433\"]}"

# 3. run scripts against tunnel in another terminal
DB_HOST=localhost DB_PORT=5433 python scripts/seed.py
DB_HOST=localhost DB_PORT=5433 python scripts/01_get_load_test_ids.py
```

---

## Consequences

- **Cost:** `t3.micro` is ~$8/month if left running. Stop the instance when not in use (`aws ec2 stop-instances --instance-ids $BASTION_ID`). Restart before tunneling (`aws ec2 start-instances --instance-ids $BASTION_ID`).
- **k6 placement:** For valid load test results, k6 must run from inside the same AWS region — either on the bastion itself or on a dedicated load generator EC2. Running k6 from a local machine against a live AWS API Gateway produces latency numbers dominated by the local internet connection, not the stack under test.
- **Production upgrade:** When upgrading to Aurora Serverless v2 + RDS Proxy, bastion usage stays the same. Only the forwarding target host changes (proxy endpoint instead of direct RDS endpoint).
