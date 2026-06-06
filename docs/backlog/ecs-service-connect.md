# ECS Service Connect for Service-to-Service Communication

## Context

ALBs removed from dev environment to cut costs (~$36/month for two idle load balancers).
With ALBs gone, newsletter Fargate tasks have no routing path to MDG Fargate tasks.
Current state: both services run at `desired_count = 0`, so no active traffic needs routing.

## Ideal Design

Replace the internal ALB with **ECS Service Connect** (AWS Cloud Map-backed mesh).

### How it works

1. Enable `service_connect_configuration` on both ECS services in the `fargate` and `fargate-mdg` modules.
2. Newsletter tasks call MDG via `http://mdg:9000` — resolved by the local service proxy sidecar injected by ECS.
3. No ALB, no target groups, no listeners needed for internal traffic.
4. External access to newsletter API can be added back selectively (e.g. a single ALB only when running load tests).

### Terraform shape (newsletter module — calls MDG)

```hcl
service_connect_configuration {
  enabled   = true
  namespace = aws_service_discovery_http_namespace.main.arn

  service {
    port_name      = "http"
    discovery_name = "newsletter"
    client_alias {
      port     = 8000
      dns_name = "newsletter"
    }
  }
}
```

### Terraform shape (mdg module — serves MDG)

```hcl
service_connect_configuration {
  enabled   = true
  namespace = aws_service_discovery_http_namespace.main.arn

  service {
    port_name      = "http"
    discovery_name = "mdg"
    client_alias {
      port     = 9000
      dns_name = "mdg"
    }
  }
}
```

### Shared namespace

A single `aws_service_discovery_http_namespace` lives in the dev env root module and its ARN is passed to both Fargate modules as a variable.

## Cost comparison

| Approach | Monthly cost |
|----------|-------------|
| 2 × ALB (current before removal) | ~$36 |
| ECS Service Connect | ~$0.01 per task-hour proxy overhead |

## When to implement

When load testing resumes and newsletter tasks need to call MDG at scale.
External ALB can be added back to newsletter module only (not MDG) at that point.
