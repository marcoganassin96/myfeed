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
