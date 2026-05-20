# ADR-005: MDG Service Auth — VPC Network Isolation

## Context

FastAPI (serving layer) calls MDG (Master Data Gateway) over internal HTTP on every cache miss. A trust boundary must be established between the two services. MDG is deployed as a private ECS Fargate service with no public ALB route.

## Options Considered

### Option A — VPC network isolation only

No application-level auth. MDG is unreachable outside the VPC private subnet. Security boundary is the AWS network layer (security groups, no public route).

**Chosen.**

### Option B — Shared API key / secret header

FastAPI sends `X-Api-Key` header on every request. MDG validates against a secret stored in AWS Secrets Manager. Revocable per caller.

**Rejected for now.** See [docs/backlog/mdg-api-key-auth.md](../backlog/mdg-api-key-auth.md) for future adoption criteria.

Reasons for deferral:
- MDG has exactly one caller (FastAPI) and no public route — network isolation provides the same security guarantee with zero overhead.
- API key adds a secret to rotate, a CI/CD env var, and auth middleware in MDG — all cost with no current benefit.
- Local development: `docker-compose up` works with no secrets config. Tests: no auth header needed in mocks.
- Option B becomes necessary only when: a second service (pipeline worker) outside the VPC needs to call MDG, or compliance requires per-caller audit logs.

### Option C — IAM / mTLS

Production-grade mutual TLS or IAM-based service identity. Standard in large-scale service meshes (App Mesh, Istio).

**Rejected.** Engineering cost far exceeds current scale and team size.

## Decision

Option A. MDG is private-subnet-only. Security group rules allow inbound on MDG port only from the FastAPI Fargate security group. No application-level auth.

## Usage

```hcl
# Terraform security group rule (FastAPI SG → MDG SG)
resource "aws_security_group_rule" "fastapi_to_mdg" {
  type                     = "ingress"
  from_port                = 9000
  to_port                  = 9000
  protocol                 = "tcp"
  source_security_group_id = var.fastapi_sg_id
  security_group_id        = aws_security_group.mdg.id
}
```

```python
# FastAPI — no auth header, plain HTTP to internal URL
async with httpx.AsyncClient(base_url=settings.MDG_URL) as client:
    resp = await client.get(f"/master-data/newsletters/{newsletter_id}")
```

## Consequences

- **Zero secret management overhead** for current scope.
- **No per-caller audit trail** — all calls are anonymous at the application layer. Mitigated by VPC Flow Logs if audit is required.
- **Future upgrade path:** add Option B (API key) when a second caller appears or compliance requires it. Migration is additive: add middleware to MDG, add header to callers, no schema change.
