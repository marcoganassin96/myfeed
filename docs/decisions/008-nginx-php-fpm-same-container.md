# ADR-008: nginx + PHP-FPM co-located in same Fargate container

## Context

MDG runs PHP 8.4 / Symfony 7 on ECS Fargate. The ALB terminates TLS and forwards plain HTTP to the container. PHP-FPM is the standard process manager for Symfony in production, but it does not speak HTTP — it speaks FastCGI (a binary framing protocol). Something must translate HTTP → FastCGI before requests reach PHP.

Three placement options exist for that translator: co-located in the same container, a sidecar container, or eliminated entirely by switching to a PHP server that speaks HTTP natively.

## Options Considered

### A — nginx co-located in same container (chosen)

nginx and php-fpm run as two processes inside one container, managed by supervisord. nginx listens on port 9000 (HTTP), forwards FastCGI to php-fpm on `127.0.0.1:9001`.

```
ALB :80 → container :9000 (nginx) → 127.0.0.1:9001 (php-fpm) → Symfony
```

**Why not ALB → php-fpm directly:** PHP-FPM does not speak HTTP. It speaks FastCGI — a binary framing protocol designed for communication between a web server and a PHP process. An ALB target group expects HTTP responses. Sending raw HTTP to php-fpm's socket produces no valid response.

**nginx's role beyond protocol translation:**
- Serves static files from `public/` without touching PHP (images, JS, CSS)
- Buffers slow client uploads so php-fpm workers are not held waiting
- Handles the `/health` endpoint with a direct `return 200` — no PHP, no DB, always fast
- Controls `client_max_body_size` before the request reaches Symfony
- `try_files $uri /index.php$is_args$args` implements Symfony's front-controller pattern: every unknown path is routed to `index.php`

**Why same container instead of sidecar:** A sidecar requires a second task definition container, cross-container networking via `localhost` bridge or `awsvpc` shared namespace, and doubles the container lifecycle surface. Co-location via supervisord is simpler, has identical network access (both processes share the same network namespace), and costs nothing extra. The trade-off is that both processes share the same CPU/memory allocation, but at MDG's traffic volume this is not a constraint.

### B — nginx as sidecar container (rejected)

ECS supports multiple containers per task. nginx could be a separate container that forwards to the php-fpm container. This adds operational complexity (two container images to build and push, two health check definitions, coordinated startup order) for no benefit at this scale. Rejected.

### C — FrankenPHP (rejected at free tier, planned for premium)

FrankenPHP is a PHP app server built on Caddy that speaks HTTP natively (no FastCGI). In worker mode it keeps the Symfony kernel resident in memory, giving 2–5× throughput over FPM. It eliminates the need for nginx entirely.

Rejected at free tier because it requires a PHP extension not available in `php:8.4-fpm-alpine`, adds build complexity, and has a smaller operational track record. Planned as the premium-tier upgrade path (see ADR-007).

## Decision

nginx co-located in the same container via supervisord. nginx on port 9000 (HTTP), php-fpm on `127.0.0.1:9001` (FastCGI, localhost only).

## Usage

Container layout:

```
ECS Task (1 container: "mdg")
└── supervisord (PID 1)
    ├── nginx   port 9000  ← ALB target
    └── php-fpm port 9001  ← localhost only, not reachable from outside
```

Config files:

| File | Purpose |
|---|---|
| `mdg/docker/nginx.conf` | nginx server block: static files, `/health`, FastCGI proxy |
| `mdg/docker/www.conf` | php-fpm pool: `listen = 127.0.0.1:9001`, worker counts |
| `mdg/docker/supervisord.conf` | Starts both processes, streams logs to stdout/stderr |

The `/health` endpoint is handled entirely by nginx:

```nginx
location = /health {
    access_log off;
    return 200 "ok";
    add_header Content-Type text/plain;
}
```

This means ALB health checks pass even if Symfony or the database is down — the check verifies the container is alive, not that the application is fully functional.

## Consequences

- **Build:** Single Docker image, single ECR repo, single ECS container definition.
- **Logs:** Both nginx and php-fpm stream to CloudWatch via the `awslogs` log driver; both appear in the same log group under the `mdg` prefix.
- **Upgrade path:** Replacing php-fpm + nginx with FrankenPHP (premium tier) requires only a Dockerfile change and supervisord removal — the ECS task definition, ALB, and Terraform module are unchanged.
- **Static files:** Any asset under `public/` is served by nginx without PHP involvement.
