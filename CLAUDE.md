# CLAUDE.md

Guidance for Claude Code when working in this repository.

App-specific standards live in sub-files:
- **Python/FastAPI** → `newsletter/CLAUDE.md`
- **PHP/Symfony** → `mdg/CLAUDE.md`

---

## Project Overview

AWS-native newsletter platform. Currently building the **API / Serving Layer** (Phase 1) with mocked data for load testing. Real NLP/LLM pipeline is out of scope until load tests pass.

**Original spec:** `docs/superpowers/specs/2026-04-23-api-serving-layer-design.md`
**Original plan:** `docs/superpowers/plans/2026-04-23-api-serving-layer.md`
**Fargate spec:** `docs/superpowers/specs/2026-05-13-fargate-serving-layer-design.md`
**Fargate plan:** `docs/superpowers/plans/2026-05-13-fargate-serving-layer.md`
**Worktree directory:** `.worktrees/` (project-local)

---

## Development Workflow (Superpowers Skills)

Use these skills in sequence for every new feature. Invoke each via the `Skill` tool **before** taking any action in that phase.

| Step | Skill | When to invoke |
|---|---|---|
| 1 | `brainstorming` | Before writing any code — refine idea, explore alternatives, save design doc |
| 2 | `using-git-worktrees` | After design approval — isolated branch, clean test baseline |
| 3 | `writing-plans` | With approved design — bite-sized tasks, exact file paths, complete code |
| 4 | `subagent-driven-development` *(preferred)* or `executing-plans` | With plan — task-by-task with review between each |
| 5 | `test-driven-development` | During implementation — RED → GREEN → REFACTOR; delete pre-test code |
| 6 | `requesting-code-review` | Between tasks — critical issues block progress |
| 7 | `finishing-a-development-branch` | All tasks done — verify tests, merge/PR/discard worktree |

Never skip `brainstorming`. Never write code before a plan exists.

---

## Decision Process — Two-Path Evaluation

For every non-trivial task (either app), evaluate two paths before writing code:

| Path | Description |
|------|-------------|
| **Ideal Design** | Best possible architecture ignoring current implementation |
| **Pragmatic Implementation** | Smallest change to current code that minimises regression risk |

Steps:

1. Write a short pros/cons table for both paths
2. Present to user — ask which to pursue
3. If **Pragmatic** chosen: implement it, then immediately create a backlog entry in `docs/backlog/` documenting the ideal design and the deferred technical debt
4. If **Ideal** chosen: implement directly; no backlog entry needed

---

## Pre-Commit Gate

Before every commit, run both validation suites. Block the commit if either fails.

```bash
# Python unit tests
cd newsletter && pytest tests/ -v

# PHP static analysis
cd mdg && composer phpstan
# PHP unit tests from mdg
composer test
```

Per-app validation details: see `newsletter/CLAUDE.md` and `mdg/CLAUDE.md`.

---

## File Structure

```
newsletter/          # Python/FastAPI API server — see newsletter/CLAUDE.md
mdg/                 # PHP/Symfony Master Data Gateway — see mdg/CLAUDE.md
load_tests/
  newsletter/        # k6 load test scripts
  mdg/               # (future PHP load tests)
scripts/             # Deployment and pipeline scripts
migrations/          # SQL schema migrations
terraform/
  modules/fargate/   # ECS Fargate, ALB, ECR, security groups, auto-scaling
  envs/dev/          # dev environment root module
infra/               # SAM template (Lambda, kept for reference)
config/              # Shared YAML config (DB, Redis, AWS)
docker-compose.yml   # Local PostgreSQL + Redis + mdg
```

---

## Local Stack

```bash
# Start all services (PostgreSQL + Redis + mdg)
docker-compose up -d

# Stop
docker-compose down
```

---

## Commit Guidelines

Format: `<type>(<scope>): <short description>`

| Type | When |
|---|---|
| `feat` | New endpoint, handler, or behaviour |
| `fix` | Bug fix |
| `test` | Add or fix tests (no production code change) |
| `infra` | SAM template, Docker, migrations |
| `chore` | Dependencies, gitignore, tooling |
| `refactor` | Code change with no behaviour change |
| `docs` | Docs, specs, plans only |

**Rules:**
- Scope = affected module (`newsletters`, `cache`, `db`, `seed`, `infra`, …)
- Max 72 characters on the first line
- Present tense, imperative mood: "add" not "added"
- Each commit leaves tests green

**Examples:**
```
feat(newsletters): add cache-miss fallback to Aurora
test(subscriptions): cover DELETE returns 204 on success
fix(cache): handle Redis unavailable without surfacing error to client
infra(sam): add RDS Proxy endpoint parameter
chore: add psycopg2-binary to requirements.txt
```

---

## Architectural Decisions

All architectural decisions are recorded in `docs/decisions/`.

**When taking an architectural decision:**

1. Add a row to [`docs/decisions/README.md`](docs/decisions/README.md):
   - `#` → next sequential number
   - `Decision` → what was decided (one phrase)
   - `Chosen` → selected option
   - `Rejected` → alternatives that were not chosen
   - `Justification` → one sentence why

2. Create `docs/decisions/NNN-slug.md` with full ADR:
   - **Context** — what forced the decision
   - **Options Considered** — each option with explicit rejection reasons
   - **Decision** — what was chosen and how it is implemented
   - **Usage** — commands or code showing how to use it
   - **Consequences** — cost, operational impact, future upgrade path

3. Commit both files together: `docs(decisions): ADR-NNN short description`

Never add an ADR detail file without updating `docs/decisions/README.md`, and vice versa.

---

## Out of Scope (Phase 1)

Do not implement, scaffold, or stub:
- NLP / clustering pipeline
- LLM newsletter generation
- Web scraping / source monitoring
- Email delivery
- Frontend / client application
