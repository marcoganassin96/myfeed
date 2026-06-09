# Architecture Decision Records

Architectural decisions are recorded here. Each decision has:
- A one-line summary and justification in this index
- A deep-dive file (`NNN-slug.md`) with full context, options considered, and consequences

When taking an architectural decision, **both this file and a new detail file must be updated** (see CLAUDE.md — Architectural Decisions).

---

## Index

| # | Decision | Chosen | Rejected | Justification |
|---|---|---|---|---|
| [001](001-bastion-ssm-for-rds-access.md) | RDS access from developer workstation | EC2 bastion + SSM port forwarding | Temporary SG rule (local machine → RDS) | Local direct access skews k6 results (uplink saturation); opening aurora SG to residential IPs is error-prone and not auditable |
| [002](002_lambda-vs-fargate.md) | Compute layer for production scale | Fargate (async FastAPI) | Lambda (current) | Lambda throttles under burst; Fargate becomes cheaper at ~44 req/s sustained; at 1000 req/s Fargate is 10× cheaper with no cold starts |
| [003](003-asyncpg-vs-psycopg3.md) | Async PostgreSQL driver for Fargate | asyncpg | psycopg3 async | asyncpg is ~1.5× faster, uses binary protocol by default, and has a more mature async connection pool; placeholder syntax migration is the only trade-off |
| [004](004-mdg-single-source-of-truth.md) | Schema ownership for Master Data Gateway | MDG owns schema via Doctrine (Option A) | Bolt-on tenant layer over existing schema (Option B) | Single owner eliminates schema drift; Doctrine global filter enforces tenant isolation at ORM level, not application discipline |
| [005](005-mdg-service-auth.md) | Service-to-service auth between FastAPI and MDG | VPC network isolation only | API key header (deferred to backlog), mTLS/IAM | MDG has no public route and one caller; network isolation provides equivalent security with zero secret-management overhead |
| [006](006-mdg-owns-redis-cache.md) | Redis cache ownership for DB-backed data | MDG owns Redis (read/write/invalidate) | FastAPI keeps Redis + MDG notifies on write, shared TTL only | Cache and data in same service; invalidation becomes a local call, not a distributed protocol; eliminates circular FastAPI↔MDG dependency |
| [007](007-mdg-compute-fargate-vs-lambda.md) | MDG compute runtime (free & premium tier) | Fargate + PHP-FPM (free); Fargate + FrankenPHP worker mode (premium) | Lambda + Bref (both tiers) | Lambda VPC cold starts and connection-per-instance exhaust db.t3.micro; provisioned concurrency costs equal Fargate with worse p99 overflow behaviour; FrankenPHP worker mode gives 2–5× throughput over FPM at no extra infra cost |
| [008](008-nginx-php-fpm-same-container.md) | HTTP frontend for PHP-FPM in Fargate | nginx co-located in same container via supervisord | ALB → PHP-FPM direct; sidecar container; FrankenPHP | PHP-FPM speaks FastCGI, not HTTP; ALB requires HTTP; nginx translates the protocol and adds static file serving, health endpoint, and request buffering at zero extra infra cost |
| [009](009-redis-removal-null-cache-adapter.md) | MDG cache backend when ElastiCache is absent | NullCacheAdapter (dev); PredisAdapter (local) | Keep ElastiCache, downgrade instance; Redis sidecar on Fargate | ElastiCache Serverless costs ~$3/day idle and cannot be stopped; NullCacheAdapter eliminates cost with zero infra and one new PHP class; Symfony env-specific DI selects the right adapter per environment |
| [010](010-laravel-admin-auth-breeze.md) | Auth strategy for Laravel admin panel | Laravel Breeze (email + password) | Cognito SSO via Socialite; No auth (VPC-only) | Didactic goal requires learning Laravel-native auth primitives; Breeze works offline with zero AWS config; Cognito SSO adds infra friction with no learning benefit at this stage |
| [011](011-laravel-admin-dual-data-access.md) | Laravel admin data access pattern | Hybrid: direct Eloquent for admins table; MdgApiClient HTTP for domain data | Full direct DB; Full API-only | Splits by bounded context — auth is admin-internal, domain data ownership stays with MDG (ADR-004); MDG becomes shared service layer for both FastAPI and Laravel |
| [012](012-endpoint-access-scopes.md) | MDG endpoint access scopes | Public (none) / User (X-User-Id) / Admin (X-Admin-Token) per endpoint | Single controller per resource with per-method guards | Role visible at file level; /admin/ prefix listener protects all admin routes with zero per-route config; split controllers eliminate scope leak risk |
