# myfeed

AWS-native newsletter platform that delivers personalised, topic-based daily digests. Events are clustered into narrative threads by an NLP pipeline; an LLM generates the daily narrative and links related past editions for context.

**Phase 1 (current):** API / Serving Layer with mocked data — load-tested to 1,000 req/s before any real pipeline is wired in.

---

## Architecture

```
Client
  │ HTTPS + Cognito JWT
  ▼
API Gateway (REST)  ──  Cognito authorizer
  ├── λ newsletters     GET /newsletters, GET /newsletters/{id}
  ├── λ subscriptions   GET / POST / DELETE /subscriptions
  ├── λ interactions    POST /interactions
  └── λ deep-dive       POST /deep-dive/{event_id}  [SSE streaming]

VPC
  ├── ElastiCache Serverless (Redis)   newsletter cache · TTL 1h
  └── Aurora Serverless v2 (Postgres)  all data · via RDS Proxy
```

Infrastructure is managed with AWS SAM (`infra/template.yaml`).

---

## Local Development

**Prerequisites:** Docker, Python 3.12, pip

```bash
# Start local Postgres + Redis
docker-compose up -d

# Install dependencies
pip install -r requirements.txt

# Apply schema
psql postgresql://newsletter:newsletter@localhost:5432/newsletter \
  -f migrations/001_initial_schema.sql

# Seed mock data and pre-warm Redis cache
python scripts/seed.py
```

---

## Running Tests

Unit tests use mocked DB and cache — no Docker required:

```bash
pytest tests/ -v
```

All tests must pass before committing. Zero failures, no unexplained skips.

---

## Load Tests

Requires a live AWS deployment. Get a token, then:

```bash
export API_URL=https://<api-id>.execute-api.eu-west-1.amazonaws.com/dev
export COGNITO_TOKEN=$(python scripts/create_test_tokens.py | head -1)
export NEWSLETTER_IDS=<comma-separated ids from seed output>
export EVENT_IDS=<comma-separated ids from seed output>

k6 run -e API_URL=$API_URL -e COGNITO_TOKEN=$COGNITO_TOKEN \
       -e NEWSLETTER_IDS=$NEWSLETTER_IDS -e EVENT_IDS=$EVENT_IDS \
       load_tests/mixed_realistic.js
```

| Scenario | Command | Must pass |
|---|---|---|
| Newsletter cached | `k6 run load_tests/newsletter_cached.js` | p99 < 50ms, 0% errors |
| Newsletter cold | `k6 run load_tests/newsletter_cold.js` | p99 < 300ms, 0% errors |
| Mixed realistic | `k6 run load_tests/mixed_realistic.js` | 1,000 req/s, p95 < 200ms |
| Deep-dive SSE | `k6 run load_tests/deep_dive_sse.js` | First chunk < 500ms |
| Cold start stress | `k6 run load_tests/cold_start_stress.js` | Error rate < 1% |

All five scenarios must pass before real data integration begins.

---

## Project Layout

```
src/
  db.py                    Aurora connection (psycopg2 + RDS Proxy)
  cache.py                 Redis client
  response.py              HTTP response builders
  handlers/
    newsletters.py
    subscriptions.py
    interactions.py
    deep_dive.py
migrations/
  001_initial_schema.sql
scripts/
  seed.py                  Truncate → insert mock data → pre-warm Redis
  create_test_tokens.py    Issue 100 Cognito Bearer tokens for load tests
load_tests/                k6 scenarios
infra/
  template.yaml            AWS SAM template
tests/
  conftest.py              pytest fixtures (mock_db, mock_cache, api_event)
docker-compose.yml         Local Postgres + Redis
```

---

## Docs

- [Design spec](docs/superpowers/specs/2026-04-23-api-serving-layer-design.md)
- [Implementation plan](docs/superpowers/plans/2026-04-23-api-serving-layer.md)
