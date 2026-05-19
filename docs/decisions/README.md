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
